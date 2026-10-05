"""Read-only access to root-published Personal Insight artifacts."""
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from config import settings
from schemas import CurrentInsightsResponse
from services.insights_validation import validate_insight_candidate

router = APIRouter(prefix="/insights", tags=["insights"])


def _current_synthesis_path() -> Path:
    return Path(settings.personal_insights_path) / "synthesized_inferences" / "current_review.json"


def _load_current_synthesis() -> CurrentInsightsResponse:
    path = _current_synthesis_path()
    if not path.is_file():
        raise HTTPException(status_code=404, detail="No current Personal Insights synthesis is saved")
    try:
        return validate_insight_candidate(json.loads(path.read_text(encoding="utf-8")), settings.personal_insights_path)
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=500, detail="Current Personal Insights synthesis is invalid") from exc


@router.get("/current", response_model=CurrentInsightsResponse)
async def get_current_insights():
    """Return the current root-published synthesis without modifying it."""
    return _load_current_synthesis()


@router.get("/status")
async def get_insights_status():
    """Authenticated readiness probe for the same artifact consumed by mobile."""
    synthesis = _load_current_synthesis()
    return {
        "status": "ready",
        "schema_version": synthesis.schema_version,
        "generated_at": synthesis.generated_at,
        "example": synthesis.example,
    }
