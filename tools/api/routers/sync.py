from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas import SyncPullResponse

router = APIRouter(prefix="/sync", tags=["sync"])


@router.get("/pull", response_model=SyncPullResponse)
async def sync_pull(db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(days=7)

    events_result = await db.execute(
        text(
            "SELECT id, title, scheduled_at, status, memo_id FROM events "
            "WHERE scheduled_at BETWEEN :now AND :end ORDER BY scheduled_at"
        ),
        {"now": now, "end": window_end},
    )
    events = [dict(r._mapping) for r in events_result.fetchall()]

    insight_result = await db.execute(
        text(
            "SELECT id, period_type, period_start::text, narrative, "
            "schedule_recommendation, accepted, generated_at "
            "FROM insights ORDER BY generated_at DESC LIMIT 1"
        )
    )
    insight_row = insight_result.fetchone()
    latest_insight = dict(insight_row._mapping) if insight_row else None

    return SyncPullResponse(events=events, latest_insight=latest_insight)
