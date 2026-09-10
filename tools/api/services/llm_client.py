"""Insight generation — narrative + schedule recommendation via local Ollama (free, no API key)."""
from __future__ import annotations

from datetime import date
import hashlib
import json

from config import settings
from database import AsyncSessionLocal
from schemas import InferenceBundle, InsightResponse, InsightSubmitRequest, PeriodType
from services.llm_context import build_context

from sqlalchemy import text


async def get_context(period: PeriodType) -> dict:
    """Raw context for the period — kept for manual/debug inspection."""
    return await build_context(period.value)


async def save_insight(
    period: PeriodType,
    submission: InsightSubmitRequest,
    memo_refs: list[str] | None = None,
    routine_adherence: dict | None = None,
    behavioral_context: str | None = None,
    inference_bundle: InferenceBundle | None = None,
    inference_context: dict | None = None,
) -> InsightResponse:
    """Persist an insight (narrative + optional schedule recommendation + enrichment fields)."""
    context = await build_context(period.value)
    period_start = date.fromisoformat(context["period_start"])
    rec = submission.schedule_recommendation

    # Merge context-derived values with explicit overrides
    _memo_refs = memo_refs if memo_refs is not None else context.get("memo_refs", [])
    _routine = routine_adherence if routine_adherence is not None else context.get("routine_adherence")
    _bctx = behavioral_context if behavioral_context is not None else context.get("behavioral_context")

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text(
                "INSERT INTO insights "
                "(period_type, period_start, narrative, schedule_recommendation, "
                " memo_refs, routine_adherence, behavioral_context, inference_bundle) "
                "VALUES (CAST(:p AS period_t), :start, :narrative, CAST(:rec AS jsonb), "
                "        CAST(:memo_refs AS uuid[]), CAST(:routine AS jsonb), :bctx, CAST(:bundle AS jsonb)) "
                "ON CONFLICT (period_type, period_start) DO UPDATE "
                "SET narrative = EXCLUDED.narrative, "
                "    schedule_recommendation = EXCLUDED.schedule_recommendation, "
                "    memo_refs = EXCLUDED.memo_refs, "
                "    routine_adherence = EXCLUDED.routine_adherence, "
                "    behavioral_context = EXCLUDED.behavioral_context, "
                "    inference_bundle = EXCLUDED.inference_bundle, "
                "    generated_at = NOW() "
                "RETURNING id, period_type, period_start::text, narrative, "
                "          schedule_recommendation, accepted, generated_at, "
                "          memo_refs, routine_adherence, behavioral_context, inference_bundle"
            ),
            {
                "p": period.value,
                "start": period_start,
                "narrative": submission.narrative,
                "rec": rec.model_dump_json() if rec else None,
                "memo_refs": [str(m) for m in (_memo_refs or [])],
                "routine": json.dumps(_routine) if _routine else None,
                "bctx": _bctx,
                "bundle": inference_bundle.model_dump_json() if inference_bundle else None,
            },
        )
        saved = dict(result.fetchone()._mapping)
        if inference_bundle:
            await _write_inference_logs(db, str(saved["id"]), inference_bundle, inference_context or context)
        await db.commit()

    return InsightResponse(**saved)


def _validate_citations(bundle: InferenceBundle, citation_catalog: list[str]) -> None:
    allowed = set(citation_catalog)
    recommendations = [
        recommendation
        for assessment in bundle.goal_review.assessments
        for recommendation in assessment.recommendations
    ]
    recommendations.extend(
        recommendation
        for group in bundle.life_pillar_review.groups
        for topic in group.topics
        for recommendation in topic.recommendations
    )
    for recommendation in recommendations:
        if recommendation.source_path not in allowed:
            raise ValueError(f"Unsupported insight citation: {recommendation.source_path}")


async def _write_inference_logs(db, insight_id: str, bundle: InferenceBundle, context: dict) -> None:
    snapshot = json.dumps(context, sort_keys=True, default=str)
    input_hash = hashlib.sha256(snapshot.encode()).hexdigest()
    sections = {
        "routine": bundle.routine_review.model_dump(mode="json"),
        "goals": bundle.goal_review.model_dump(mode="json"),
        "future_plans": bundle.future_plan_review.model_dump(mode="json"),
        "life_pillars": bundle.life_pillar_review.model_dump(mode="json"),
    }
    citations = [
        support.source_path
        for assessment in bundle.goal_review.assessments
        for support in assessment.recommendations
    ]
    citations.extend(
        support.source_path
        for group in bundle.life_pillar_review.groups
        for topic in group.topics
        for support in topic.recommendations
    )
    for inference_type, output in sections.items():
        await db.execute(
            text(
                "INSERT INTO insight_inference_logs "
                "(insight_id, inference_type, schema_version, status, input_hash, input_snapshot, output, citation_paths, model) "
                "VALUES (CAST(:insight_id AS uuid), :type, :version, 'valid', :hash, CAST(:snapshot AS jsonb), "
                "CAST(:output AS jsonb), CAST(:citations AS jsonb), :model)"
            ),
            {"insight_id": insight_id, "type": inference_type, "version": bundle.schema_version,
             "hash": input_hash, "snapshot": snapshot, "output": json.dumps(output),
             "citations": json.dumps(citations), "model": settings.ollama_planning_model},
        )


async def _write_failed_inference_logs(context: dict, status: str, error_message: str) -> None:
    """Record an attempted manual review without replacing the last valid review."""
    snapshot = json.dumps(context, sort_keys=True, default=str)
    input_hash = hashlib.sha256(snapshot.encode()).hexdigest()
    try:
        async with AsyncSessionLocal() as db:
            for inference_type in ("routine", "goals", "future_plans", "life_pillars"):
                await db.execute(
                    text(
                        "INSERT INTO insight_inference_logs "
                        "(inference_type, schema_version, status, input_hash, input_snapshot, model, error_message) "
                        "VALUES (:type, '1.2', :status, :hash, CAST(:snapshot AS jsonb), :model, :error)"
                    ),
                    {"type": inference_type, "status": status, "hash": input_hash,
                     "snapshot": snapshot, "model": settings.ollama_planning_model,
                     "error": error_message[:2000]},
                )
            await db.commit()
    except Exception:
        # Preserve the original generation error; audit failure must not hide it.
        return
