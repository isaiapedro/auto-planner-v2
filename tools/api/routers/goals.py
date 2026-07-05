from datetime import date

from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from database import get_db
from schemas import Goal, GoalCreate, GoalStatus

router = APIRouter(prefix="/goals", tags=["goals"])


@router.post("", response_model=Goal, status_code=201)
async def create_goal(body: GoalCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text(
            "INSERT INTO goals (title, kind, domain, target_date, cadence) "
            "VALUES (:title, CAST(:kind AS goal_kind_t), :domain, "
            "        CAST(:target_date AS date), :cadence) "
            "RETURNING id, title, kind, domain, target_date::text, cadence, "
            "          status, created_at, updated_at"
        ),
        {
            "title": body.title,
            "kind": body.kind.value,
            "domain": body.domain,
            "target_date": date.fromisoformat(body.target_date) if body.target_date else None,
            "cadence": body.cadence,
        },
    )
    row = result.fetchone()
    await db.commit()
    return dict(row._mapping)


@router.get("", response_model=list[Goal])
async def list_goals(status: GoalStatus | None = None, db: AsyncSession = Depends(get_db)):
    query = (
        "SELECT id, title, kind, domain, target_date::text, cadence, "
        "       status, created_at, updated_at FROM goals "
    )
    params = {}
    if status:
        query += "WHERE status = CAST(:status AS goal_status_t) "
        params["status"] = status.value
    query += "ORDER BY created_at DESC"

    result = await db.execute(text(query), params)
    return [dict(r._mapping) for r in result.fetchall()]


@router.patch("/{goal_id}/status", response_model=Goal)
async def update_goal_status(goal_id: str, status: GoalStatus, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text(
            "UPDATE goals SET status = CAST(:status AS goal_status_t), updated_at = NOW() "
            "WHERE id = CAST(:id AS uuid) "
            "RETURNING id, title, kind, domain, target_date::text, cadence, "
            "          status, created_at, updated_at"
        ),
        {"status": status.value, "id": goal_id},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Goal not found")
    await db.commit()
    return dict(row._mapping)
