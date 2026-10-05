from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


# --- enums ---

class EventStatus(str, Enum):
    pending = "pending"
    confirmed = "confirmed"
    skipped = "skipped"


# --- memo ---

class MemoUploadResponse(BaseModel):
    job_id: str
    status: str = "queued"


class MemoStatusResponse(BaseModel):
    job_id: str
    status: str  # queued | transcribing | done | error
    error: str | None = None


class MemoHistoryItem(BaseModel):
    id: UUID
    status: str
    event_title: str | None = None
    created_at: datetime
    recorded_at_known: bool = True
    transcript: str | None = None
    error: str | None = None


# --- events ---

class EventConfirmRequest(BaseModel):
    confirmed: bool
    memo_id: UUID | None = None


class CalendarBlockCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    scheduled_at: datetime
    duration_minutes: int = Field(ge=5, le=1_440)


class EventResponse(BaseModel):
    id: UUID
    title: str
    scheduled_at: datetime
    duration_minutes: int = Field(default=60, ge=5, le=1_440)
    status: EventStatus
    memo_id: UUID | None = None


class LiveCalendarEvent(BaseModel):
    """A read-only Google Calendar occurrence for the authenticated device."""

    id: str
    title: str
    start: str
    end: str
    all_day: bool = False


# --- shared planning inputs ---

class FixedBlock(BaseModel):
    title: str
    days: list[str]
    start: str
    duration_minutes: int


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


# --- insights ---

class InsightContractModel(BaseModel):
    """Reject LLM-added or mistyped fields at the saved-artifact boundary."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ReviewFinding(InsightContractModel):
    statement: str
    evidence_paths: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low", "none"]


class ScientificSupport(InsightContractModel):
    claim: str
    source_path: str
    applicability: str


class RoutineReview(InsightContractModel):
    summary: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    worked: list[ReviewFinding] = Field(default_factory=list)
    did_not_work: list[ReviewFinding] = Field(default_factory=list)
    experiments: list[str] = Field(default_factory=list)


class GoalAssessment(InsightContractModel):
    id: str | None = None
    priority_key: str | None = None
    status: Literal["evidenced", "scheduled", "partially_evidenced", "not_tracked", "at_risk", "complete"]
    evidence_paths: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low", "none"]
    findings: list[ReviewFinding] = Field(default_factory=list)
    recommendations: list[ScientificSupport] = Field(default_factory=list)

    @model_validator(mode="after")
    def identifies_one_registry_target(self) -> "GoalAssessment":
        if bool(self.id) == bool(self.priority_key):
            raise ValueError("each goal assessment must set exactly one of id or priority_key")
        return self


class GoalReview(InsightContractModel):
    registry_path: Literal["../archive/long_term_goals.md"]
    summary: str
    assessments: list[GoalAssessment] = Field(default_factory=list)


class FuturePlanReview(InsightContractModel):
    summary: str
    progress_updates: list[ReviewFinding] = Field(default_factory=list)
    new_additions: list[ReviewFinding] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    # Additive 1.2 fields.  They record an observed relationship between
    # registered planning targets; they are not instructions or diagnoses.
    conflicts: list["GoalRelationship"] = Field(default_factory=list)
    facilitators: list["GoalRelationship"] = Field(default_factory=list)


class GoalReference(InsightContractModel):
    """One canonical planning target participating in a review relationship."""

    id: str | None = None
    priority_key: str | None = None

    @model_validator(mode="after")
    def identifies_one_registry_target(self) -> "GoalReference":
        if bool(self.id) == bool(self.priority_key):
            raise ValueError("each relationship target must set exactly one of id or priority_key")
        return self


class GoalRelationship(InsightContractModel):
    """A cited, observational connection between two or more registered targets."""

    statement: str
    targets: list[GoalReference] = Field(min_length=2)
    evidence_paths: list[str] = Field(min_length=1)
    confidence: Literal["high", "medium", "low"]

    @model_validator(mode="after")
    def has_distinct_targets(self) -> "GoalRelationship":
        keys = [target.id or target.priority_key for target in self.targets]
        if len(keys) != len(set(keys)):
            raise ValueError("relationship targets must be distinct")
        return self


class InferenceBundle(InsightContractModel):
    schema_version: Literal["1.2"]
    routine_review: RoutineReview
    goal_review: GoalReview
    future_plan_review: FuturePlanReview
    life_pillar_review: "LifePillarReview"


class PillarTopic(InsightContractModel):
    name: str
    status: Literal["tracked", "partially_tracked", "not_tracked"]
    evidence_paths: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low", "none"]
    findings: list[ReviewFinding] = Field(default_factory=list)
    recommendations: list[ScientificSupport] = Field(default_factory=list)


class PillarGroup(InsightContractModel):
    name: str
    topics: list[PillarTopic]


class LifePillarReview(InsightContractModel):
    summary: str
    groups: list[PillarGroup]


class CurrentInsightsResponse(InsightContractModel):
    schema_version: Literal["1.2"]
    generated_at: datetime
    source_files: list[str]
    example: bool = False
    narrative: str
    inference_bundle: InferenceBundle

    @model_validator(mode="after")
    def has_unique_nonempty_source_paths(self) -> "CurrentInsightsResponse":
        if not self.source_files or len(self.source_files) != len(set(self.source_files)):
            raise ValueError("source_files must be non-empty and unique")
        if any(not source.startswith("personal/planner/") for source in self.source_files):
            raise ValueError("source_files must remain within personal/planner/")
        return self


# --- sync ---

class SyncPullResponse(BaseModel):
    events: list[EventResponse]
