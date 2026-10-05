from datetime import datetime, timedelta, timezone

LOCAL_TZ = timezone(timedelta(hours=-3))

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas import SyncPullResponse

router = APIRouter(prefix="/sync", tags=["sync"])


@router.get("/pull", response_model=SyncPullResponse)
async def sync_pull(db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    local_now = now.astimezone(LOCAL_TZ)
    window_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    window_end = local_now.replace(hour=23, minute=59, second=59, microsecond=999999).astimezone(timezone.utc)

    events_result = await db.execute(
        text(
            "SELECT id, title, scheduled_at, duration_minutes, status, memo_id FROM events "
            "WHERE scheduled_at BETWEEN :start AND :end ORDER BY scheduled_at"
        ),
        {"start": window_start, "end": window_end},
    )
    events = [dict(r._mapping) for r in events_result.fetchall()]

    return SyncPullResponse(events=events)
