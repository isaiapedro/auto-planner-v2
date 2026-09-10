import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services.planning.orchestrator import (
    accept_planning_run,
    create_planning_run,
    get_planning_run,
    reject_planning_run,
    validate_planning_run,
)
from services.planning.schemas import AcceptPlanningResponse, PlanningRunResponse, PlanningWeekRequest

router = APIRouter(prefix="/planning", tags=["planning"])
logger = logging.getLogger(__name__)


@router.post("/week", response_model=PlanningRunResponse, status_code=201)
async def create_week_plan(body: PlanningWeekRequest, db: AsyncSession = Depends(get_db)):
    try:
        return await create_planning_run(db, body)
    except Exception as exc:
        logger.exception("Failed to create planning run")
        raise HTTPException(status_code=500, detail="Planning could not be created. Please try again.") from exc


@router.get("/{run_id}", response_model=PlanningRunResponse)
async def get_plan(run_id: UUID, db: AsyncSession = Depends(get_db)):
    try:
        return await get_planning_run(db, run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Planning run not found") from exc


@router.post("/{run_id}/validate", response_model=PlanningRunResponse)
async def validate_plan(run_id: UUID, db: AsyncSession = Depends(get_db)):
    try:
        return await validate_planning_run(db, run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Planning run not found") from exc


@router.post("/{run_id}/accept", response_model=AcceptPlanningResponse)
async def accept_plan(run_id: UUID, db: AsyncSession = Depends(get_db)):
    try:
        run, event_ids = await accept_planning_run(db, run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Planning run not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to accept planning run")
        raise HTTPException(status_code=502, detail="Calendar service is temporarily unavailable. Please try again.") from exc
    return AcceptPlanningResponse(
        status=run.status,
        blocks_applied=len(event_ids),
        calendar_event_ids=event_ids,
    )


@router.post("/{run_id}/reject", response_model=PlanningRunResponse)
async def reject_plan(run_id: UUID, db: AsyncSession = Depends(get_db)):
    try:
        return await reject_planning_run(db, run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Planning run not found") from exc
