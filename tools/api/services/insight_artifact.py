"""Validated, atomic storage for the Personal Insights mobile artifact."""
from __future__ import annotations

import json
import os
from uuid import uuid4
from datetime import datetime, timezone
from pathlib import Path

from config import settings
from schemas import CurrentInsightsResponse


_COMPONENTS = (
    ("routine_review", "routine_review.json"),
    ("goal_review", "goal_review.json"),
    ("future_plan_review", "future_plan_review.json"),
    ("life_pillar_review", "life_pillar_review.json"),
)


def write_current_review(review: CurrentInsightsResponse) -> CurrentInsightsResponse:
    """Validate and replace the complete read-only review as one coherent snapshot.

    Components live in an immutable versioned snapshot. ``current_review.json``
    is atomically replaced only after that snapshot is complete, so a reader
    always follows one aggregate artifact to components from the same review.
    """
    directory = Path(settings.personal_insights_path) / "synthesized_inferences"
    snapshot_id = uuid4().hex
    snapshot_directory = directory / "snapshots" / snapshot_id
    snapshot_directory.mkdir(parents=True, exist_ok=False)
    source_files = [
        f"personal/planner/insights/synthesized_inferences/snapshots/{snapshot_id}/{name}"
        for _, name in _COMPONENTS
    ]
    normalized = review.model_copy(
        update={
            "generated_at": datetime.now(timezone.utc),
            "source_files": source_files,
        }
    )
    for field, filename in _COMPONENTS:
        _atomic_json_write(
            snapshot_directory / filename,
            getattr(normalized.inference_bundle, field).model_dump(mode="json"),
        )
    _atomic_json_write(directory / "current_review.json", normalized.model_dump(mode="json"))
    return normalized


def _atomic_json_write(path: Path, content: object) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(content, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
