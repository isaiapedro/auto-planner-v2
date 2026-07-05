import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas import AcceptRecommendationResponse, InsightResponse, InsightSubmitRequest, PeriodType
from services import calendar as calendar_svc
from services.llm_client import generate_and_save_insight, get_context, save_insight

router = APIRouter(prefix="/insights", tags=["insights"])
logger = logging.getLogger(__name__)


@router.get("/{period}", response_model=InsightResponse)
async def get_insight(period: PeriodType, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text(
            "SELECT id, period_type, period_start::text, narrative, "
            "schedule_recommendation, accepted, generated_at "
            "FROM insights "
            "WHERE period_type = :period "
            "ORDER BY period_start DESC LIMIT 1"
        ),
        {"period": period.value},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No insight generated yet for this period")
    return dict(row._mapping)


@router.get("/{period}/context")
async def get_insight_context(period: PeriodType):
    """Raw context to paste into a Claude Code session for manual review generation."""
    return await get_context(period)


@router.post("/{period}/submit", response_model=InsightResponse)
async def submit_insight(period: PeriodType, body: InsightSubmitRequest):
    """Store a narrative/recommendation generated manually (debug/override path)."""
    return await save_insight(period, body)


@router.post("/{period}/generate", response_model=InsightResponse)
async def generate_insight(period: PeriodType):
    """Cron entrypoint — generates and stores the review automatically via local Ollama."""
    return await generate_and_save_insight(period)


@router.post("/schedule/accept", response_model=AcceptRecommendationResponse)
async def accept_schedule_recommendation(db: AsyncSession = Depends(get_db)):
    # Fetch latest unaccepted recommendation
    result = await db.execute(
        text(
            "SELECT id, schedule_recommendation FROM insights "
            "WHERE accepted = false AND schedule_recommendation IS NOT NULL "
            "ORDER BY generated_at DESC LIMIT 1"
        )
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No pending schedule recommendation")

    rec = row.schedule_recommendation
    blocks = rec.get("blocks", []) if rec else []

    applied = 0
    for block in blocks:
        try:
            await _apply_block(db, block)
            applied += 1
        except Exception:
            logger.exception("Failed to apply schedule_recommendation block %r", block)

    await db.execute(
        text("UPDATE insights SET accepted = true WHERE id = :id"),
        {"id": str(row.id)},
    )
    await db.commit()

    return AcceptRecommendationResponse(accepted=True, blocks_applied=applied)


async def _apply_block(db: AsyncSession, block: dict) -> None:
    action = block.get("action")

    if action == "add":
        google_event_id = await asyncio.to_thread(
            calendar_svc.create_event,
            block["title"],
            block["scheduled_at"],
            block.get("duration_minutes") or 30,
        )
        await db.execute(
            text(
                "INSERT INTO events (title, scheduled_at, google_event_id, calendar_id) "
                "VALUES (:title, :scheduled_at, :gid, :cal)"
            ),
            {
                "title": block["title"],
                "scheduled_at": block["scheduled_at"],
                "gid": google_event_id,
                "cal": calendar_svc.DEFAULT_CALENDAR_ID,
            },
        )

    elif action == "move":
        row = await db.execute(
            text("SELECT google_event_id, calendar_id FROM events WHERE id = CAST(:id AS uuid)"),
            {"id": block["block_id"]},
        )
        existing = row.fetchone()
        if not existing:
            raise ValueError(f"move: no event {block['block_id']}")
        if existing.google_event_id:
            await asyncio.to_thread(
                calendar_svc.update_event_time,
                existing.google_event_id,
                block["new"],
                block.get("duration_minutes"),
                existing.calendar_id or calendar_svc.DEFAULT_CALENDAR_ID,
            )
        await db.execute(
            text("UPDATE events SET scheduled_at = :new WHERE id = CAST(:id AS uuid)"),
            {"new": block["new"], "id": block["block_id"]},
        )

    elif action == "remove":
        row = await db.execute(
            text("SELECT google_event_id, calendar_id FROM events WHERE id = CAST(:id AS uuid)"),
            {"id": block["block_id"]},
        )
        existing = row.fetchone()
        if not existing:
            raise ValueError(f"remove: no event {block['block_id']}")
        if existing.google_event_id:
            await asyncio.to_thread(
                calendar_svc.delete_event,
                existing.google_event_id,
                existing.calendar_id or calendar_svc.DEFAULT_CALENDAR_ID,
            )
        await db.execute(
            text("DELETE FROM events WHERE id = CAST(:id AS uuid)"),
            {"id": block["block_id"]},
        )
