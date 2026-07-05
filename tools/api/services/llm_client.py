"""Insight generation — narrative + schedule recommendation via local Ollama (free, no API key)."""
from __future__ import annotations

from datetime import date

from database import AsyncSessionLocal
from schemas import InsightResponse, InsightSubmitRequest, PeriodType, ScheduleRecommendation
from services import ollama as ollama_svc
from services.llm_context import build_context

from sqlalchemy import text


async def get_context(period: PeriodType) -> dict:
    """Raw context for the period — kept for manual/debug inspection."""
    return await build_context(period.value)


async def generate_and_save_insight(period: PeriodType) -> InsightResponse:
    """Cron entrypoint: build context, generate narrative+recommendation via Ollama, persist."""
    context = await build_context(period.value)
    result = await ollama_svc.generate_insight(context)
    submission = InsightSubmitRequest(
        narrative=result["narrative"],
        schedule_recommendation=ScheduleRecommendation(**result["schedule_recommendation"])
        if result.get("schedule_recommendation")
        else None,
    )
    return await save_insight(period, submission)


async def save_insight(period: PeriodType, submission: InsightSubmitRequest) -> InsightResponse:
    """Persist a manually-generated insight (narrative + optional schedule recommendation)."""
    context = await build_context(period.value)
    period_start = date.fromisoformat(context["period_start"])
    rec = submission.schedule_recommendation

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text(
                "INSERT INTO insights (period_type, period_start, narrative, schedule_recommendation) "
                "VALUES (CAST(:p AS period_t), :start, :narrative, CAST(:rec AS jsonb)) "
                "ON CONFLICT (period_type, period_start) DO UPDATE "
                "SET narrative = EXCLUDED.narrative, "
                "    schedule_recommendation = EXCLUDED.schedule_recommendation, "
                "    generated_at = NOW() "
                "RETURNING id, period_type, period_start::text, narrative, "
                "          schedule_recommendation, accepted, generated_at"
            ),
            {
                "p": period.value,
                "start": period_start,
                "narrative": submission.narrative,
                "rec": rec.model_dump_json() if rec else None,
            },
        )
        saved = dict(result.fetchone()._mapping)
        await db.commit()

    return InsightResponse(**saved)
