import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from fastapi import Query
from config import settings
from schemas import CurrentInsightsResponse, InferenceLogResponse, InsightResponse, InsightSubmitRequest, PeriodType
from services.llm_client import get_context
from services.insight_artifact import write_current_review

router = APIRouter(prefix="/insights", tags=["insights"])


_INSIGHT_COLS = (
    "id, period_type, period_start::text, narrative, "
    "schedule_recommendation, accepted, generated_at, "
    "COALESCE(memo_refs, '{}') AS memo_refs, "
    "routine_adherence, behavioral_context, inference_bundle"
)


@router.get("/current", response_model=CurrentInsightsResponse)
async def get_current_insights():
    """Return the current validated synthesis stored in the Personal domain."""
    path = Path(settings.personal_insights_path) / "synthesized_inferences" / "current_review.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="No current Personal Insights synthesis is saved")
    try:
        return CurrentInsightsResponse.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=500, detail="Current Personal Insights synthesis is invalid") from exc


@router.put("/current", response_model=CurrentInsightsResponse)
async def save_current_insights(body: CurrentInsightsResponse):
    """Save a fully validated, read-only Personal synthesis for the mobile app."""
    return write_current_review(body)


@router.get("/{period}/history", response_model=list[InsightResponse])
async def get_insight_history(
    period: PeriodType,
    limit: int = Query(default=10, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text(
            f"SELECT {_INSIGHT_COLS} FROM insights "
            "WHERE period_type = :period "
            "ORDER BY period_start DESC "
            "LIMIT :limit OFFSET :offset"
        ),
        {"period": period.value, "limit": limit, "offset": offset},
    )
    return [dict(r._mapping) for r in result.fetchall()]


@router.get("/{period}", response_model=InsightResponse)
async def get_insight(period: PeriodType, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text(
            f"SELECT {_INSIGHT_COLS} FROM insights "
            "WHERE period_type = :period "
            "ORDER BY period_start DESC LIMIT 1"
        ),
        {"period": period.value},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No saved insight for this period")
    return dict(row._mapping)


@router.get("/{period}/context")
async def get_insight_context(period: PeriodType):
    """Return inspectable collection metadata without exposing raw evidence."""
    context = await get_context(period)
    return {
        "period": context["period"],
        "period_start": context["period_start"],
        "summary": context["summary"],
        "memo_count": len(context["memo_refs"]),
        "goal_count": len(context["goals"]),
        "scheduled_goal_count": len(context["scheduled_goals"]),
        "pillar_group_count": len(context["pillar_taxonomy"]),
        "routine_available": context["routine_adherence"] is not None,
        "citation_count": len(context["citation_catalog"]),
    }


@router.get("/{insight_id}/inferences", response_model=list[InferenceLogResponse])
async def get_inference_logs(insight_id: str, db: AsyncSession = Depends(get_db)):
    """Read-only, append-only audit history for a selected review."""
    result = await db.execute(
        text(
            "SELECT id, inference_type, schema_version, status, input_hash, output, "
            "citation_paths, model, error_message, created_at "
            "FROM insight_inference_logs WHERE insight_id = CAST(:id AS uuid) "
            "ORDER BY created_at DESC"
        ),
        {"id": insight_id},
    )
    return [dict(row._mapping) for row in result.fetchall()]


@router.post("/{period}/submit", response_model=InsightResponse)
async def submit_insight(period: PeriodType, body: InsightSubmitRequest):
    """Store a narrative/recommendation generated manually (debug/override path)."""
    return await save_insight(period, body)
