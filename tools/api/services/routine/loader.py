from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from config import settings

logger = logging.getLogger(__name__)

DEFAULT_ROUTINE_CALENDAR = Path(settings.personal_insights_path) / "routine_objects" / "routine_calendar.json"


class RoutineCalendarEvent(BaseModel):
    date: str
    weekday: str | None = None
    day_theme: str | None = None
    start: str
    end: str
    title: str
    category: str | None = None
    notes: str | None = None


class RoutineCalendar(BaseModel):
    source_markdown: str
    version: str
    week_start: str
    week_end: str
    timezone: str = "America/Sao_Paulo"
    event_count: int
    events: list[RoutineCalendarEvent] = Field(default_factory=list)


def load_routine_calendar(path: Path | None = None) -> RoutineCalendar:
    candidates: list[Path] = [path] if path else [DEFAULT_ROUTINE_CALENDAR]

    calendar_path: Path | None = None
    for candidate in candidates:
        if candidate.exists():
            calendar_path = candidate
            break

    if calendar_path is None:
        tried = ", ".join(str(item) for item in candidates)
        raise FileNotFoundError(f"Routine calendar not found. Tried: {tried}")

    raw = json.loads(calendar_path.read_text(encoding="utf-8"))
    logger.info("Loaded routine calendar from %s (%d events)", calendar_path, len(raw.get("events", [])))
    return RoutineCalendar.model_validate(raw)


def duration_minutes(start: str, end: str) -> int:
    start_dt = datetime.strptime(start, "%H:%M")
    end_dt = datetime.strptime(end, "%H:%M")
    delta = int((end_dt - start_dt).total_seconds() // 60)
    if delta <= 0:
        raise ValueError(f"Invalid time range {start}–{end}")
    return delta
