from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas import EventConfirmRequest, EventResponse, EventStatus

router = APIRouter(prefix="/events", tags=["events"])


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
            "WHERE id = :id RETURNING id, title, scheduled_at, status, memo_id"
        ),
        {"status": status.value, "memo_id": str(body.memo_id) if body.memo_id else None, "id": str(event_id)},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Event not found")
    await db.commit()
    return dict(row._mapping)
