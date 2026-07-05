from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# --- enums ---

class EventStatus(str, Enum):
    pending = "pending"
    confirmed = "confirmed"
    skipped = "skipped"


class PeriodType(str, Enum):
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"


class SentimentType(str, Enum):
    positive = "positive"
    neutral = "neutral"
    negative = "negative"


# --- memo ---

class MemoUploadResponse(BaseModel):
    job_id: str
    status: str = "queued"


class MemoStatusResponse(BaseModel):
    job_id: str
    status: str  # queued | transcribing | extracting | embedding | done | error
    error: str | None = None


# --- features (Ollama structured output) ---

class Entity(BaseModel):
    name: str
    type: str  # person | project | concept | location


class MemoFeatures(BaseModel):
    mood: float = Field(ge=0.0, le=1.0)
    energy: float = Field(ge=0.0, le=1.0)
    topics: list[str]
    entities: list[Entity]
    sentiment: SentimentType
    key_takeaways: list[str]
    event_confirmed: bool = False


# --- events ---

class EventConfirmRequest(BaseModel):
    confirmed: bool
    memo_id: str | None = None


class EventResponse(BaseModel):
    id: UUID
    title: str
    scheduled_at: datetime
    status: EventStatus
    memo_id: UUID | None = None


# --- schedule ---

class FixedBlock(BaseModel):
    title: str
    days: list[str]   # ["monday", "wednesday"]
    start: str        # "09:00"
    duration_minutes: int


class ScheduleConfigRequest(BaseModel):
    wake_time: str    # "06:30"
    sleep_time: str   # "23:00"
    buffer_minutes: int = 60   # unscheduled off-time before sleep_time
    # Deprecated — allocation is now goal-driven (see GoalCreate/Goal below).
    # Kept optional so old clients/rows don't break; new wizard sends {}.
    domain_weights: dict[str, float] = {}
    fixed_blocks: list[FixedBlock]


class ScheduleConfigResponse(ScheduleConfigRequest):
    id: UUID
    updated_at: datetime


# --- goals ---

class GoalKind(str, Enum):
    long_term = "long_term"
    routine = "routine"


class GoalStatus(str, Enum):
    active = "active"
    achieved = "achieved"
    paused = "paused"


class GoalCreate(BaseModel):
    title: str
    kind: GoalKind
    domain: str | None = None
    target_date: str | None = None   # ISO date, long_term goals only
    cadence: str | None = None       # e.g. "daily", "3x/week" — routine goals only


class Goal(GoalCreate):
    id: UUID
    status: GoalStatus
    created_at: datetime
    updated_at: datetime


# --- dashboard ---

class DashboardMetric(BaseModel):
    metric_id: str
    value: float
    computed_for_date: str
    metadata: dict[str, Any] = {}


class DashboardResponse(BaseModel):
    metrics: list[DashboardMetric]


# --- schedule recommendation diff ---

class BlockChange(BaseModel):
    action: str         # add | move | remove
    block_id: str | None = None
    field: str | None = None
    old: Any | None = None
    new: Any | None = None
    title: str | None = None
    domain: str | None = None
    scheduled_at: datetime | None = None
    duration_minutes: int | None = None


class ScheduleRecommendation(BaseModel):
    reasoning: str
    blocks: list[BlockChange]


# --- insights ---

class InsightResponse(BaseModel):
    id: UUID
    period_type: PeriodType
    period_start: str
    narrative: str
    schedule_recommendation: ScheduleRecommendation | None = None
    accepted: bool
    generated_at: datetime


class InsightSubmitRequest(BaseModel):
    narrative: str
    schedule_recommendation: ScheduleRecommendation | None = None


class AcceptRecommendationResponse(BaseModel):
    accepted: bool
    blocks_applied: int


# --- sync ---

class SyncPullResponse(BaseModel):
    events: list[EventResponse]
    latest_insight: InsightResponse | None = None
