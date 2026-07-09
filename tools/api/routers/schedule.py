import asyncio
import json
import logging
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database import AsyncSessionLocal, get_db
from schemas import ScheduleConfigRequest, ScheduleConfigResponse
from services import calendar as calendar_svc
from services import slots as slots_svc

router = APIRouter(prefix="/schedule", tags=["schedule"])
logger = logging.getLogger(__name__)


@router.post("", response_model=ScheduleConfigResponse, status_code=201)
async def create_schedule(
    body: ScheduleConfigRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    # Create each fixed_block as a real recurring Google Calendar event.
    # Best-effort — a calendar failure (e.g. OAuth not set up yet) shouldn't
    # block saving the schedule itself.
    event_ids = []
    for block in body.fixed_blocks:
        try:
            event_id = await asyncio.to_thread(
                calendar_svc.create_recurring_event,
                block.title,
                block.start,
                block.days,
                block.duration_minutes,
            )
            event_ids.append(event_id)
        except Exception:
            logger.exception("Failed to create calendar event for fixed_block %r", block.title)

    result = await db.execute(
        text(
            "INSERT INTO schedule_config (wake_time, sleep_time, buffer_minutes, domain_weights, fixed_blocks, calendar_event_ids) "
            "VALUES (:wake, :sleep, :buffer, CAST(:weights AS jsonb), CAST(:blocks AS jsonb), CAST(:event_ids AS jsonb)) "
            "RETURNING id, wake_time, sleep_time, buffer_minutes, domain_weights, fixed_blocks, calendar_event_ids, updated_at"
        ),
        {
            "wake": datetime.strptime(body.wake_time, "%H:%M").time(),
            "sleep": datetime.strptime(body.sleep_time, "%H:%M").time(),
            "buffer": body.buffer_minutes,
            "weights": json.dumps(body.domain_weights),
            "blocks": "[" + ",".join(b.model_dump_json() for b in body.fixed_blocks) + "]",
            "event_ids": json.dumps(event_ids),
        },
    )
    row = result.fetchone()
    schedule_id = str(row.id)
    await db.commit()

    # Two-block model (see pios_v2_architecture.md §11.1): T(E) = A - T(F).
    # Slot generation + validity is deterministic code (services/slots.py) —
    # the LLM only assigns goals to pre-vetted slots, never touches raw times.
    # Runs in the background so the request returns immediately.
    background_tasks.add_task(
        _allocate_exploration_blocks,
        schedule_id,
        body.wake_time,
        body.sleep_time,
        body.buffer_minutes,
        body.fixed_blocks,
    )

    return _serialize_row(row)

async def _allocate_exploration_blocks(
    schedule_id: str, wake_time: str, sleep_time: str, buffer_minutes: int, fixed_blocks
) -> None:
    async with AsyncSessionLocal() as db:
        goal_rows = await db.execute(
            text("SELECT title, kind::text, domain, target_date::text, cadence FROM goals WHERE status = 'active'")
        )
        goals = [dict(r._mapping) for r in goal_rows.fetchall()]
    
    if not goals:
        return

    try:
        busy_windows = await asyncio.to_thread(calendar_svc.summarize_busy_windows, days_ahead=14)
    except Exception:
        logger.exception("Failed to summarize busy windows for exploration allocation")
        busy_windows = []

    slots = slots_svc.generate_weekly_slots(
        wake_time, sleep_time, buffer_minutes, [b.model_dump() for b in fixed_blocks], busy_windows
    )
    if not slots:
        return

    assignments = slots_svc.assign_slots_to_goals(slots, goals)
    slots_by_id = {s["id"]: s for s in slots}
    new_event_ids = []
    
    for assignment in assignments:
        slot = slots_by_id.get(assignment["slot_id"])
        if slot is None:
            continue
        try:
            event_id = await asyncio.to_thread(
                calendar_svc.create_recurring_event,
                assignment["goal_title"],
                slot["start"],
                [slot["weekday"]],
                slot["duration_minutes"],
            )
            new_event_ids.append(event_id)
        except Exception:
            logger.exception("Failed to create calendar event for slot assignment %r", assignment)

    if new_event_ids:
        async with AsyncSessionLocal() as db:
            await db.execute(
                text(
                    "UPDATE schedule_config "
                    "SET calendar_event_ids = calendar_event_ids || CAST(:new_ids AS jsonb) "
                    "WHERE id = CAST(:id AS uuid)"
                ),
                {"new_ids": json.dumps(new_event_ids), "id": schedule_id},
            )
            await db.commit()

@router.get("", response_model=ScheduleConfigResponse)
async def get_schedule(db: AsyncSession = Depends(get_db)):
    # FIX: Explicitly select buffer_minutes and calendar_event_ids
    result = await db.execute(
        text("SELECT id, wake_time, sleep_time, buffer_minutes, domain_weights, fixed_blocks, calendar_event_ids, updated_at "
             "FROM schedule_config ORDER BY updated_at DESC LIMIT 1")
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No schedule configured!")
    return _serialize_row(row)


def _serialize_row(row) -> dict:
    data = dict(row._mapping)
    data["wake_time"] = data["wake_time"].strftime("%H:%M")
    data["sleep_time"] = data["sleep_time"].strftime("%H:%M")
    return data
