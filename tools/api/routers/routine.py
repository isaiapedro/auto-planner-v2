import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services.routine.applier import apply_routine_week, sync_routine_events_local
from services.routine.loader import RoutineCalendar, load_routine_calendar

router = APIRouter(prefix="/routine", tags=["routine"])
logger = logging.getLogger(__name__)


class RoutineApplyResponse(BaseModel):
    batch_id: str
    week_start: str
    week_end: str
    source_markdown: str
    events_created: int
    events_failed: int
    events_existing: int = 0
    google_calendar_written: bool = True
    calendar_event_ids: list[str] = Field(default_factory=list)
    events: list[dict] = Field(default_factory=list)
    existing_events: list[dict] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)


@router.get("/week", response_model=RoutineCalendar)
async def get_routine_week():
    try:
        return load_routine_calendar()
    except FileNotFoundError as exc:
        logger.exception("Routine calendar source is unavailable")
        raise HTTPException(status_code=404, detail="Routine calendar is not available") from exc


@router.post("/apply", response_model=RoutineApplyResponse)
async def apply_routine(db: AsyncSession = Depends(get_db)):
    try:
        result = await apply_routine_week(db)
        return RoutineApplyResponse.model_validate(result)
    except FileNotFoundError as exc:
        logger.exception("Routine calendar source is unavailable")
        raise HTTPException(status_code=404, detail="Routine calendar is not available") from exc
    except Exception as exc:
        logger.exception("Failed to apply routine week")
        raise HTTPException(status_code=500, detail="Routine could not be applied. Please try again.") from exc


@router.post("/sync-local", response_model=RoutineApplyResponse)
async def sync_routine_local(db: AsyncSession = Depends(get_db)):
    try:
        result = await sync_routine_events_local(db)
        return RoutineApplyResponse.model_validate(result)
    except FileNotFoundError as exc:
        logger.exception("Routine calendar source is unavailable")
        raise HTTPException(status_code=404, detail="Routine calendar is not available") from exc
    except Exception as exc:
        logger.exception("Failed to sync routine events locally")
        raise HTTPException(status_code=500, detail="Routine could not be synced. Please try again.") from exc
