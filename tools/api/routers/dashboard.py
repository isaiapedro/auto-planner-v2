from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas import DashboardMetric, DashboardResponse

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
async def get_dashboard(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text(
            "SELECT metric_id, metric_value, computed_for_date::text, metadata "
            "FROM dashboard_metrics "
            "WHERE computed_for_date = (SELECT MAX(computed_for_date) FROM dashboard_metrics) "
            "ORDER BY metric_id"
        )
    )
    rows = result.fetchall()
    metrics = [
        DashboardMetric(
            metric_id=r.metric_id,
            value=r.metric_value,
            computed_for_date=r.computed_for_date,
            metadata=r.metadata or {},
        )
        for r in rows
    ]
    return DashboardResponse(metrics=metrics)
