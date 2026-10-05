from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services import calendar as calendar_svc
from services.routine.loader import RoutineCalendar, RoutineCalendarEvent, duration_minutes, load_routine_calendar

logger = logging.getLogger(__name__)
LOCAL_TZ = ZoneInfo("America/Sao_Paulo")


def _scheduled_at(date: str, start: str) -> datetime:
    return datetime.strptime(f"{date} {start}", "%Y-%m-%d %H:%M").replace(tzinfo=LOCAL_TZ)


def _event_description(event: RoutineCalendarEvent) -> str | None:
    parts: list[str] = []
    if event.day_theme:
        parts.append(f"Day theme: {event.day_theme}")
    if event.category:
        parts.append(f"Category: {event.category}")
    if event.notes:
        parts.append(event.notes)
    parts.append("Source: personal/planner/insights/routine_objects/routine.md")
    return "\n".join(parts) if parts else None


async def apply_routine_week(db: AsyncSession, calendar: RoutineCalendar | None = None) -> dict:
    routine = calendar or load_routine_calendar()
    return await _persist_routine(db, routine, write_google_calendar=True)


async def sync_routine_events_local(db: AsyncSession, calendar: RoutineCalendar | None = None) -> dict:
    routine = calendar or load_routine_calendar()
    return await _persist_routine(db, routine, write_google_calendar=False)


async def _persist_routine(
    db: AsyncSession,
    routine: RoutineCalendar,
    *,
    write_google_calendar: bool,
) -> dict:
    created: list[dict] = []
    existing: list[dict] = []
    errors: list[dict] = []
    created_google_events: list[str] = []

    try:
        if write_google_calendar:
            # Validate once before a potentially large mutation batch. This
            # does not change Google Calendar.
            await asyncio.to_thread(calendar_svc.verify_default_calendar_access)
        for event in routine.events:
            inserted_here = False
            routine_key = ""
            try:
                key_material = "\x1f".join((routine.source_markdown, event.date, event.start, event.end, event.title))
                routine_key = hashlib.sha256(key_material.encode("utf-8")).hexdigest()
                scheduled_at = _scheduled_at(event.date, event.start)
                inserted = await db.execute(
                    text(
                        "INSERT INTO events (title, scheduled_at, duration_minutes, status, routine_key) "
                        "VALUES (:title, :scheduled_at, :duration_minutes, 'pending', :routine_key) "
                        "ON CONFLICT (routine_key) WHERE routine_key IS NOT NULL DO NOTHING "
                        "RETURNING id"
                    ),
                    {
                        "title": event.title,
                        "scheduled_at": scheduled_at,
                        "duration_minutes": duration_minutes(event.start, event.end),
                        "routine_key": routine_key,
                    },
                )
                if inserted.scalar_one_or_none() is None:
                    existing.append({"date": event.date, "start": event.start, "title": event.title})
                    continue
                inserted_here = True
                minutes = duration_minutes(event.start, event.end)
                start_iso = f"{event.date}T{event.start}:00"
                google_id: str | None = None
                if write_google_calendar:
                    google_id = await asyncio.to_thread(
                        calendar_svc.create_event,
                        event.title,
                        start_iso,
                        minutes,
                        calendar_svc.DEFAULT_CALENDAR_ID,
                        _event_description(event),
                    )
                    created_google_events.append(google_id)
                    await db.execute(
                        text("UPDATE events SET google_event_id = :google_event_id, calendar_id = :calendar_id "
                             "WHERE routine_key = :routine_key"),
                        {"google_event_id": google_id, "calendar_id": calendar_svc.DEFAULT_CALENDAR_ID, "routine_key": routine_key},
                    )
                created.append(
                    {
                        "date": event.date,
                        "start": event.start,
                        "end": event.end,
                        "title": event.title,
                        "google_event_id": google_id,
                    }
                )
            except Exception as exc:
                if inserted_here:
                    # Do not leave a local idempotency marker for an external
                    # creation that failed; the user must be able to retry.
                    await db.execute(
                        text("DELETE FROM events WHERE routine_key = :routine_key"),
                        {"routine_key": routine_key},
                    )
                logger.warning("Failed to create routine event %s %s: %s", event.date, event.title, exc)
                errors.append({
                    "date": event.date,
                    "title": event.title,
                    "error": "Calendar event could not be created. Please retry.",
                })
        await db.commit()
    except Exception:
        await db.rollback()
        # Google has no shared transaction with PostgreSQL.  Compensate any
        # freshly-created external events if the local commit failed, so a
        # retry cannot create an invisible duplicate.
        for google_event_id in created_google_events:
            try:
                await asyncio.to_thread(calendar_svc.delete_event, google_event_id, calendar_svc.DEFAULT_CALENDAR_ID)
            except Exception:
                logger.exception("Could not compensate Google Calendar event %s", google_event_id)
        raise

    batch_id = str(uuid4())
    logger.info(
        "Routine week applied batch=%s created=%d errors=%d week=%s..%s",
        batch_id,
        len(created),
        len(errors),
        routine.week_start,
        routine.week_end,
    )
    return {
        "batch_id": batch_id,
        "week_start": routine.week_start,
        "week_end": routine.week_end,
        "source_markdown": routine.source_markdown,
        "events_created": len(created),
        "events_failed": len(errors),
        "events_existing": len(existing),
        "google_calendar_written": write_google_calendar,
        "calendar_event_ids": [
            item["google_event_id"] for item in created if item.get("google_event_id")
        ],
        "events": created,
        "existing_events": existing,
        "errors": errors,
    }
