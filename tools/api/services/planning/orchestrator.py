from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from services import availability
from services import calendar as calendar_svc
from services.planning.evidence_planner import build_recommendations, revise_recommendations
from services.planning.intention_parser import interpret_intention
from services.planning.pipeline_trace import PipelineTracer
from services.planning.plan_narrative import build_plan_summary
from services.planning.repair import repair_schedule
from services.planning.scheduler import schedule_week
from services.planning.schemas import (
    EvidenceItem,
    GeneratedSchedule,
    PlanningRunResponse,
    PlanningStatus,
    PlanningWeekRequest,
    PipelineMeta,
    PipelineStageTrace,
    RepairAttempt,
)
from services.planning.validator import validate_schedule
from services.wiki.service import WikiService

wiki_service = WikiService()
logger = logging.getLogger(__name__)


async def create_planning_run(db: AsyncSession, body: PlanningWeekRequest) -> PlanningRunResponse:
    trace = PipelineTracer(settings.ollama_planning_model)
    week_start = date.fromisoformat(body.week_start) if body.week_start else availability.planning_window_start()
    week_end = week_start + timedelta(days=settings.planning_horizon_days - 1)
    fixed_blocks = [block.model_dump() for block in body.fixed_blocks]

    started = trace.start()
    interpreted, intention_source = await interpret_intention(body.user_intention)
    trace.record(
        "intentions",
        intention_source,
        started,
        input_summary={"user_intention_chars": len(body.user_intention)},
        output_summary={
            "intention_count": len(interpreted.intentions),
            "intentions": [
                {"id": item.id, "theme": item.theme, "frequency": item.desired_frequency}
                for item in interpreted.intentions
            ],
        },
        notes=[
            "LLM timed out or failed → phrase-based fallback splits your text into intentions.",
            "If themes look duplicated later, check the recommendations stage next.",
        ]
        if intention_source == "fallback"
        else [],
    )

    search_terms = " ".join(
        [body.user_intention]
        + [intention.theme for intention in interpreted.intentions]
        + interpreted.desired_routines
    )
    started = trace.start()
    evidence = wiki_service.search(
        query=search_terms,
        domains=["planning_science", "health", "technology", "business", "media", "arts"],
        categories=["wiki", "papers", "concepts", "raw", "general"],
        limit=8,
    )
    trace.record(
        "wiki_retrieval",
        "deterministic",
        started,
        input_summary={"query_preview": search_terms[:160]},
        output_summary={
            "evidence_hits": len(evidence.items),
            "evidence_ids": [item.evidence_id for item in evidence.items[:5]],
        },
        notes=[
            "Zero hits → evidence planner skips LLM and uses enriched fallback.",
            f"Knowledge root: {settings.knowledge_root_path}",
        ]
        if not evidence.items
        else [],
    )

    started = trace.start()
    recommendations, recommendation_source = await build_recommendations(body.user_intention, interpreted, evidence)
    recommendation_models = recommendations.recommendations
    trace.record(
        "recommendations",
        recommendation_source,
        started,
        input_summary={"intention_count": len(interpreted.intentions), "evidence_hits": len(evidence.items)},
        output_summary={
            "recommendation_count": len(recommendation_models),
            "recommendations": [
                {
                    "intention_id": item.intention_id,
                    "title": item.title,
                    "frequency": item.frequency,
                    "duration_minutes": item.duration_minutes,
                }
                for item in recommendation_models
            ],
        },
        notes=[
            "Ollama returned empty JSON → deterministic fallback recommendations.",
            "Titles should be distinct per intention; if not, check intention themes.",
        ]
        if recommendation_source == "fallback"
        else [],
    )

    try:
        calendar_events = await asyncio.to_thread(calendar_svc.list_upcoming_events, settings.planning_horizon_days + 7)
    except Exception:
        calendar_events = []

    started = trace.start()
    week_availability = availability.compute_week_availability(
        week_start=week_start,
        horizon_days=settings.planning_horizon_days,
        wake_time=body.wake_time,
        sleep_time=body.sleep_time,
        buffer_minutes=body.buffer_minutes,
        fixed_blocks=fixed_blocks,
        calendar_events=calendar_events,
    )
    fixed_for_week = availability.summarize_fixed_blocks_for_week(
        week_start=week_start,
        horizon_days=settings.planning_horizon_days,
        fixed_blocks=fixed_blocks,
    )
    free_interval_count = sum(len(day.get("free_intervals", [])) for day in week_availability)
    trace.record(
        "availability",
        "deterministic",
        started,
        input_summary={
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "calendar_events": len(calendar_events),
            "fixed_blocks": len(fixed_blocks),
        },
        output_summary={
            "free_interval_count": free_interval_count,
            "days_with_availability": sum(1 for day in week_availability if day.get("free_intervals")),
        },
    )

    started = trace.start()
    generated = schedule_week(recommendation_models, week_availability, fixed_for_week)
    unique_titles = {block.title for block in generated.exploration_blocks}
    trace.record(
        "scheduler",
        "deterministic",
        started,
        input_summary={"recommendation_count": len(recommendation_models)},
        output_summary={
            "exploration_blocks": len(generated.exploration_blocks),
            "fixed_blocks": len(generated.fixed_blocks),
            "unique_titles": sorted(unique_titles),
            "title_counts": _title_counts(generated.exploration_blocks),
        },
        notes=[
            "Repeated titles usually mean recommendations collapsed to the same practice label.",
        ]
        if len(unique_titles) < max(len(recommendation_models), 1)
        else [],
    )
    validation = validate_schedule(
        generated,
        recommendation_models,
        week_start,
        week_end,
        body.wake_time,
        body.sleep_time,
        body.buffer_minutes,
    )
    repair_history: list[RepairAttempt] = []

    attempts = 0
    while not validation.valid and attempts < settings.planning_repair_attempts:
        repaired, history = repair_schedule(generated, validation, week_availability)
        repair_history.extend(history)
        generated = repaired
        validation = validate_schedule(
            generated,
            recommendation_models,
            week_start,
            week_end,
            body.wake_time,
            body.sleep_time,
            body.buffer_minutes,
        )
        attempts += 1

    if not validation.valid:
        recommendations = await revise_recommendations(
            body.user_intention,
            interpreted,
            evidence,
            recommendations,
            [item.model_dump() for item in validation.violations],
        )
        recommendation_models = recommendations.recommendations
        recommendation_source = "llm_repair"
        generated = schedule_week(recommendation_models, week_availability, fixed_for_week)
        validation = validate_schedule(
            generated,
            recommendation_models,
            week_start,
            week_end,
            body.wake_time,
            body.sleep_time,
            body.buffer_minutes,
        )
        repair_history.append(
            RepairAttempt(strategy="llm_requirements_revision", detail="Revised planning requirements after deterministic repair failed.")
        )

    status = PlanningStatus.ready_for_review if validation.valid else PlanningStatus.needs_repair

    started = trace.start()
    trace.record(
        "validation",
        "deterministic",
        started,
        output_summary={
            "valid": validation.valid,
            "violation_count": len(validation.violations),
            "violations": [item.model_dump() for item in validation.violations[:5]],
            "repair_steps": len(repair_history),
        },
        notes=[
            f"Repair loop ran {len(repair_history)} step(s) before this validation result.",
        ]
        if repair_history
        else [],
    )

    pipeline_meta = PipelineMeta(
        intention_source=intention_source,
        recommendation_source=recommendation_source,
        evidence_hits=len(evidence.items),
        exploration_blocks=len(generated.exploration_blocks),
        recommendations=len(recommendation_models),
        planning_model=settings.ollama_planning_model,
        unique_exploration_titles=len({block.title for block in generated.exploration_blocks}),
    )
    started = trace.start()
    plan_summary, recommendation_models = await build_plan_summary(
        body.user_intention,
        interpreted,
        recommendation_models,
        generated,
        evidence,
        pipeline_meta,
    )
    summary_source = "llm" if intention_source == "llm" and recommendation_source == "llm" else "template"
    trace.record(
        "plan_summary",
        summary_source,
        started,
        output_summary={
            "summary_chars": len(plan_summary or ""),
            "summary_preview": (plan_summary or "")[:180],
        },
        notes=[
            "Template summary used because at least one upstream stage used deterministic fallback.",
        ]
        if summary_source == "template"
        else [],
    )
    title_by_intention = {item.intention_id: item.title for item in recommendation_models if item.title}
    for block in generated.exploration_blocks:
        if block.intention_id in title_by_intention:
            block.title = title_by_intention[block.intention_id] or block.title
    unique_title_count = len({block.title for block in generated.exploration_blocks})
    pipeline_meta = pipeline_meta.model_copy(
        update={
            "exploration_blocks": len(generated.exploration_blocks),
            "recommendations": len(recommendation_models),
            "unique_exploration_titles": unique_title_count,
        }
    )

    payload = {
        "user_intention": body.user_intention,
        "wake_time": body.wake_time,
        "sleep_time": body.sleep_time,
        "buffer_minutes": body.buffer_minutes,
        "fixed_blocks": fixed_blocks,
        "interpreted_intentions": interpreted.model_dump(),
        "evidence_package_query": evidence.query,
        "evidence_package": [item.model_dump() for item in evidence.items],
        "evidence_items": [item.model_dump() for item in evidence.items],
        "recommendations": [item.model_dump() for item in recommendation_models],
        "generated_schedule": generated.model_dump(),
        "validation_result": validation.model_dump(),
        "repair_history": [item.model_dump() for item in repair_history],
        "pipeline_meta": pipeline_meta.model_dump(),
        "plan_summary": plan_summary,
        "pipeline_trace": [item.model_dump() for item in trace.to_list()],
        "calendar_event_ids": [],
    }

    result = await db.execute(
        text(
            """
            INSERT INTO planning_runs (
                week_start, week_end, status, user_intention, payload
            ) VALUES (
                :week_start, :week_end, :status, :user_intention, CAST(:payload AS jsonb)
            )
            RETURNING id, created_at, updated_at
            """
        ),
        {
            "week_start": week_start,
            "week_end": week_end,
            "status": status.value,
            "user_intention": body.user_intention,
            "payload": json.dumps(payload),
        },
    )
    row = result.fetchone()
    await db.commit()
    response = _serialize_run(row.id, week_start, week_end, status, body.user_intention, payload, row.created_at, row.updated_at)
    logger.info(
        "Planning run created id=%s week=%s..%s status=%s intention_source=%s recommendation_source=%s "
        "intentions=%d recommendations=%d fixed_blocks=%d exploration_blocks=%d valid=%s violations=%d "
        "repair_steps=%d calendar_events=%d free_intervals=%d evidence_hits=%d unique_titles=%d",
        response.id,
        week_start.isoformat(),
        week_end.isoformat(),
        status.value,
        intention_source,
        recommendation_source,
        len(interpreted.intentions),
        len(recommendation_models),
        len(generated.fixed_blocks),
        len(generated.exploration_blocks),
        validation.valid,
        len(validation.violations),
        len(repair_history),
        len(calendar_events),
        free_interval_count,
        len(evidence.items),
        pipeline_meta.unique_exploration_titles,
    )
    if not generated.exploration_blocks:
        logger.warning(
            "Planning run %s finished with zero exploration blocks (recommendations=%d free_intervals=%d)",
            response.id,
            len(recommendation_models),
            free_interval_count,
        )
    return response


async def get_planning_run(db: AsyncSession, run_id: UUID) -> PlanningRunResponse:
    row = await _fetch_run(db, run_id)
    payload = row["payload"]
    return _serialize_run(
        row["id"],
        row["week_start"],
        row["week_end"],
        PlanningStatus(row["status"]),
        row["user_intention"],
        payload,
        row["created_at"],
        row["updated_at"],
    )


async def validate_planning_run(db: AsyncSession, run_id: UUID) -> PlanningRunResponse:
    row = await _fetch_run(db, run_id)
    payload = row["payload"]
    from services.planning.schemas import PlanningRecommendation

    recommendations = [PlanningRecommendation.model_validate(item) for item in payload["recommendations"]]
    generated = GeneratedSchedule.model_validate(payload["generated_schedule"])
    week_start = row["week_start"]
    week_end = row["week_end"]
    validation = validate_schedule(
        generated,
        recommendations,
        week_start,
        week_end,
        payload["wake_time"],
        payload["sleep_time"],
        payload["buffer_minutes"],
    )
    payload["validation_result"] = validation.model_dump()
    status = PlanningStatus.validated if validation.valid else PlanningStatus.needs_repair
    await _update_run(db, run_id, status, payload)
    return _serialize_run(
        row["id"],
        week_start,
        week_end,
        status,
        row["user_intention"],
        payload,
        row["created_at"],
        datetime.utcnow(),
    )


async def accept_planning_run(db: AsyncSession, run_id: UUID) -> tuple[PlanningRunResponse, list[str]]:
    row = await _fetch_run(db, run_id)
    payload = row["payload"]
    validation = payload.get("validation_result", {})
    if not validation.get("valid"):
        raise ValueError("Planning run is not valid and cannot be applied.")

    generated = GeneratedSchedule.model_validate(payload["generated_schedule"])
    event_ids: list[str] = []
    for block in generated.exploration_blocks:
        start_iso = f"{block.date}T{block.start}:00"
        event_id = await asyncio.to_thread(
            calendar_svc.create_event,
            block.title,
            start_iso,
            _to_minutes(block.end) - _to_minutes(block.start),
        )
        event_ids.append(event_id)

        await db.execute(
            text(
                """
                INSERT INTO events (title, scheduled_at, duration_minutes, status, google_event_id)
                VALUES (:title, CAST(:scheduled_at AS timestamptz), :duration_minutes, 'pending', :google_event_id)
                """
            ),
            {
                "title": block.title,
                "scheduled_at": start_iso,
                "duration_minutes": _to_minutes(block.end) - _to_minutes(block.start),
                "google_event_id": event_id,
            },
        )

    payload["calendar_event_ids"] = event_ids
    await _update_run(db, run_id, PlanningStatus.applied, payload)
    response = _serialize_run(
        row["id"],
        row["week_start"],
        row["week_end"],
        PlanningStatus.applied,
        row["user_intention"],
        payload,
        row["created_at"],
        datetime.utcnow(),
    )
    await db.commit()
    return response, event_ids


async def reject_planning_run(db: AsyncSession, run_id: UUID) -> PlanningRunResponse:
    row = await _fetch_run(db, run_id)
    payload = row["payload"]
    await _update_run(db, run_id, PlanningStatus.rejected, payload)
    await db.commit()
    return _serialize_run(
        row["id"],
        row["week_start"],
        row["week_end"],
        PlanningStatus.rejected,
        row["user_intention"],
        payload,
        row["created_at"],
        datetime.utcnow(),
    )


async def _fetch_run(db: AsyncSession, run_id: UUID) -> dict:
    result = await db.execute(
        text(
            """
            SELECT id, week_start, week_end, status, user_intention, payload, created_at, updated_at
            FROM planning_runs
            WHERE id = CAST(:id AS uuid)
            """
        ),
        {"id": str(run_id)},
    )
    row = result.fetchone()
    if not row:
        raise KeyError("Planning run not found")
    data = dict(row._mapping)
    if isinstance(data["payload"], str):
        data["payload"] = json.loads(data["payload"])
    return data


async def _update_run(db: AsyncSession, run_id: UUID, status: PlanningStatus, payload: dict) -> None:
    await db.execute(
        text(
            """
            UPDATE planning_runs
            SET status = :status,
                payload = CAST(:payload AS jsonb),
                updated_at = NOW()
            WHERE id = CAST(:id AS uuid)
            """
        ),
        {"id": str(run_id), "status": status.value, "payload": json.dumps(payload)},
    )


def _title_counts(blocks: list) -> dict[str, int]:
    counts: dict[str, int] = {}
    for block in blocks:
        counts[block.title] = counts.get(block.title, 0) + 1
    return counts


def _serialize_run(
    run_id: UUID,
    week_start: date,
    week_end: date,
    status: PlanningStatus,
    user_intention: str,
    payload: dict,
    created_at: datetime,
    updated_at: datetime,
) -> PlanningRunResponse:
    from services.planning.schemas import (
        EvidenceRecommendations,
        InterpretedIntentions,
        PlanningRecommendation,
        ValidationResult,
    )

    recommendations = [PlanningRecommendation.model_validate(item) for item in payload["recommendations"]]
    evidence_items = [EvidenceItem.model_validate(item) for item in payload.get("evidence_items", payload.get("evidence_package", []))]
    pipeline_meta = PipelineMeta.model_validate(
        payload.get(
            "pipeline_meta",
            {
                "intention_source": "unknown",
                "recommendation_source": "unknown",
                "evidence_hits": len(evidence_items),
                "exploration_blocks": len(payload.get("generated_schedule", {}).get("exploration_blocks", [])),
                "recommendations": len(recommendations),
                "planning_model": settings.ollama_planning_model,
                "unique_exploration_titles": 0,
            },
        )
    )
    pipeline_trace = [
        PipelineStageTrace.model_validate(item) for item in payload.get("pipeline_trace", [])
    ]
    return PlanningRunResponse(
        id=run_id,
        status=status,
        week_start=week_start.isoformat(),
        week_end=week_end.isoformat(),
        user_intention=user_intention,
        interpreted_intentions=InterpretedIntentions.model_validate(payload["interpreted_intentions"]),
        evidence_package_query=payload["evidence_package_query"],
        evidence_items=evidence_items,
        recommendations=recommendations,
        generated_schedule=GeneratedSchedule.model_validate(payload["generated_schedule"]),
        validation_result=ValidationResult.model_validate(payload["validation_result"]),
        repair_history=[RepairAttempt.model_validate(item) for item in payload.get("repair_history", [])],
        pipeline_meta=pipeline_meta,
        plan_summary=payload.get("plan_summary"),
        pipeline_trace=pipeline_trace,
        created_at=created_at,
        updated_at=updated_at,
    )


def _to_minutes(hhmm: str) -> int:
    hour, minute = hhmm.split(":")
    return int(hour) * 60 + int(minute)
