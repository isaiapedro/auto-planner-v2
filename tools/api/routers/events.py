import asyncio
import logging
from datetime import date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas import CalendarBlockCreate, EventConfirmRequest, EventResponse, EventStatus
from services import calendar as calendar_svc

router = APIRouter(prefix="/events", tags=["events"])
logger = logging.getLogger(__name__)
LOCAL_TZ = ZoneInfo("America/Sao_Paulo")


@router.get("", response_model=list[EventResponse])
async def get_events(
    start: date,
    end: date,
    db: AsyncSession = Depends(get_db),
):
    """Return local Planner events in a half-open date range [start, end).

    Calendar reads only persisted Planner blocks. It never contacts Google, so
    opening a week remains responsive and cannot expose external calendar data.
    """
    if end <= start:
        raise HTTPException(status_code=422, detail="end must be after start")
    if end - start > timedelta(days=31):
        raise HTTPException(status_code=422, detail="date range cannot exceed 31 days")
    range_start = datetime.combine(start, time.min, tzinfo=LOCAL_TZ)
    range_end = datetime.combine(end, time.min, tzinfo=LOCAL_TZ)
    result = await db.execute(
        text(
            "SELECT id, title, scheduled_at, duration_minutes, status, memo_id FROM events "
            "WHERE scheduled_at >= :start AND scheduled_at < :end ORDER BY scheduled_at"
        ),
        {"start": range_start, "end": range_end},
    )
    return [dict(row._mapping) for row in result.fetchall()]


@router.post("", response_model=EventResponse, status_code=201)
async def create_event(body: CalendarBlockCreate, db: AsyncSession = Depends(get_db)):
    """Create one deliberate calendar block in Google and the local schedule."""
    try:
        google_event_id = await asyncio.to_thread(
            calendar_svc.create_event,
            body.title,
            body.scheduled_at.isoformat(),
            body.duration_minutes,
        )
    except Exception as exc:
        logger.exception("Google Calendar event creation failed")
        raise HTTPException(
            status_code=502,
            detail="Calendar service is temporarily unavailable. Please try again.",
        ) from exc

    result = await db.execute(
        text(
            "INSERT INTO events (title, scheduled_at, duration_minutes, status, google_event_id, calendar_id) "
            "VALUES (:title, :scheduled_at, :duration_minutes, 'pending', :google_event_id, :calendar_id) "
            "RETURNING id, title, scheduled_at, duration_minutes, status, memo_id"
        ),
        {"title": body.title, "scheduled_at": body.scheduled_at, "duration_minutes": body.duration_minutes, "google_event_id": google_event_id,
         "calendar_id": calendar_svc.DEFAULT_CALENDAR_ID},
    )
    await db.commit()
    return dict(result.fetchone()._mapping)


@router.post("/{event_id}/confirm")
async def confirm_event(
    event_id: UUID,
    body: EventConfirmRequest,
    db: AsyncSession = Depends(get_db),
):
    status = EventStatus.confirmed if body.confirmed else EventStatus.skipped
    result = await db.execute(
        text(
            "UPDATE events SET status = :status, memo_id = :memo_id "
            "WHERE id = :id RETURNING id, title, scheduled_at, duration_minutes, status, memo_id"
        ),
        {"status": status.value, "memo_id": str(body.memo_id) if body.memo_id else None, "id": str(event_id)},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Event not found")
    await db.commit()
    return dict(row._mapping)
