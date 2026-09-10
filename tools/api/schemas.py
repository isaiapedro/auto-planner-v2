from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
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
    transcript: str | None = None
    error: str | None = None


# --- command-triggered Personal account triage ---

AccountProposalKind = Literal[
    "planner_future_task",
    "career_note",
    "finance_note",
    "knowledge_technology_research_request",
    "manual_review",
]
AccountProposalTarget = Literal[
    "personal_planner",
    "personal_career_strategy",
    "personal_finance",
    "knowledge_technology",
]
AccountProposalStatus = Literal["proposed", "accepted", "dismissed"]


class AccountTriageRequest(BaseModel):
    """An explicit request to analyse already-completed Personal memo IDs only."""

    memo_ids: list[UUID] = Field(min_length=1, max_length=20)
    instruction: str | None = Field(default=None, max_length=500)


class AccountProposalResponse(BaseModel):
    id: UUID
    run_id: UUID
    kind: AccountProposalKind
    target: AccountProposalTarget
    title: str
    summary: str
    confidence: Literal["high", "medium", "low"]
    status: AccountProposalStatus
    requires_confirmation: bool = True
    memo_ids: list[UUID]
    created_at: datetime
    resolved_at: datetime | None = None


class AccountTriageRunResponse(BaseModel):
    id: UUID
    status: Literal["completed", "needs_manual_review"]
    memo_ids: list[UUID]
    proposal_ids: list[UUID]
    used_llm: bool
    created_at: datetime


class AccountAuditEventResponse(BaseModel):
    """Metadata-only account lifecycle event.

    This intentionally has no memo IDs, transcript identifiers/hashes, prompt
    material, file paths, or adapter payloads. It is safe for an authenticated
    account audit timeline.
    """

    event_id: UUID
    event_type: Literal[
        "triage_started", "triage_completed", "triage_fallback",
        "catalog_denied", "proposal_accepted", "proposal_dismissed",
    ]
    occurred_at: datetime
    run_id: UUID | None = None
    proposal_id: UUID | None = None
    proposal_kind: AccountProposalKind | None = None
    target: AccountProposalTarget | None = None
    memo_count: int | None = Field(default=None, ge=0, le=20)
    proposal_count: int | None = Field(default=None, ge=0, le=12)
    duration_ms: int | None = Field(default=None, ge=0)
    model_id: str | None = None
    outcome: Literal["started", "completed", "fallback", "accepted", "dismissed", "denied"]
    error_class: str | None = None


class AccountRunAuditResponse(BaseModel):
    """Redacted provenance and lifecycle timeline for one triage run."""

    run_id: UUID
    status: Literal["completed", "needs_manual_review"]
    created_at: datetime
    model_id: str | None = None
    catalog_sha256: str
    catalog_schema_version: str
    triage_schema_version: str
    instruction_sha256: str
    duration_ms: int | None = Field(default=None, ge=0)
    outcome: Literal["completed", "fallback"]
    events: list[AccountAuditEventResponse] = Field(default_factory=list)


class CatalogContextResource(BaseModel):
    """A declared relative context document; its content is never returned."""

    path: str


class AccountDestination(BaseModel):
    id: str
    path: str
    repository_id: str
    privacy: Literal["personal_only", "objective_reference"]
    readable_context: list[CatalogContextResource] = Field(default_factory=list)
    proposal_capabilities: list[str] = Field(default_factory=list)


class AccountCatalogResponse(BaseModel):
    schema_version: Literal["1.0"]
    catalog_path: str
    # A SHA-256 over the mounted declarative contracts and every approved
    # manifest/context file. It is safe to expose: it contains no file content
    # or absolute path, but lets runs prove exactly which contract revision
    # authorized them.
    catalog_fingerprint: str
    destinations: list[AccountDestination]


# --- events ---

class EventConfirmRequest(BaseModel):
    confirmed: bool
    memo_id: str | None = None


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


class ScheduleRecommendation(BaseModel):
    reasoning: str
    blocks: list[BlockChange]


# --- insights ---

class ReviewFinding(BaseModel):
    statement: str
    evidence_paths: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low", "none"]


class ScientificSupport(BaseModel):
    claim: str
    source_path: str
    applicability: str


class RoutineReview(BaseModel):
    summary: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    worked: list[ReviewFinding] = Field(default_factory=list)
    did_not_work: list[ReviewFinding] = Field(default_factory=list)
    experiments: list[str] = Field(default_factory=list)


class GoalAssessment(BaseModel):
    id: str | None = None
    priority_key: str | None = None
    status: Literal["evidenced", "scheduled", "partially_evidenced", "not_tracked", "at_risk", "complete"]
    evidence_paths: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low", "none"]
    findings: list[ReviewFinding] = Field(default_factory=list)
    recommendations: list[ScientificSupport] = Field(default_factory=list)


class GoalReview(BaseModel):
    registry_path: Literal["../archive/long_term_goals.md"]
    summary: str
    assessments: list[GoalAssessment] = Field(default_factory=list)


class FuturePlanReview(BaseModel):
    summary: str
    progress_updates: list[ReviewFinding] = Field(default_factory=list)
    new_additions: list[ReviewFinding] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)


class InferenceBundle(BaseModel):
    schema_version: Literal["1.2"]
    routine_review: RoutineReview
    goal_review: GoalReview
    future_plan_review: FuturePlanReview
    life_pillar_review: "LifePillarReview"


class PillarTopic(BaseModel):
    name: str
    status: Literal["tracked", "partially_tracked", "not_tracked"]
    evidence_paths: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low", "none"]
    findings: list[ReviewFinding] = Field(default_factory=list)
    recommendations: list[ScientificSupport] = Field(default_factory=list)


class PillarGroup(BaseModel):
    name: str
    topics: list[PillarTopic]


class LifePillarReview(BaseModel):
    summary: str
    groups: list[PillarGroup]


class InferenceLogResponse(BaseModel):
    id: UUID
    inference_type: Literal["routine", "goals", "future_plans", "life_pillars"]
    schema_version: str
    status: Literal["valid", "invalid", "failed"]
    input_hash: str
    output: dict[str, Any] | None = None
    citation_paths: list[str] = Field(default_factory=list)
    model: str | None = None
    error_message: str | None = None
    created_at: datetime

class InsightResponse(BaseModel):
    id: UUID
    period_type: PeriodType
    period_start: str
    narrative: str
    schedule_recommendation: ScheduleRecommendation | None = None
    accepted: bool
    generated_at: datetime
    memo_refs: list[UUID] = []
    routine_adherence: dict | None = None
    behavioral_context: str | None = None
    inference_bundle: InferenceBundle | None = None


class InsightSubmitRequest(BaseModel):
    narrative: str
    schedule_recommendation: ScheduleRecommendation | None = None


class CurrentInsightsResponse(BaseModel):
    schema_version: Literal["1.2"]
    generated_at: datetime
    source_files: list[str]
    example: bool = False
    narrative: str
    inference_bundle: InferenceBundle


class AcceptRecommendationResponse(BaseModel):
    accepted: bool
    blocks_applied: int


# --- sync ---

class SyncPullResponse(BaseModel):
    events: list[EventResponse]
    latest_insight: InsightResponse | None = None
