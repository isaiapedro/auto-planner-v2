from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from schemas import FixedBlock


class PlanningStatus(str, Enum):
    draft = "draft"
    validated = "validated"
    needs_repair = "needs_repair"
    ready_for_review = "ready_for_review"
    accepted = "accepted"
    applied = "applied"
    rejected = "rejected"


class InterpretedIntention(BaseModel):
    id: str
    theme: str
    desired_frequency: int = Field(ge=1, le=14)
    preferred_duration_minutes: int = Field(ge=15, le=240)
    priority: str = "medium"


class PlanningPreference(BaseModel):
    key: str
    value: str


class PlanningConstraint(BaseModel):
    key: str
    value: str


class InterpretedIntentions(BaseModel):
    intentions: list[InterpretedIntention] = Field(default_factory=list)
    preferences: list[PlanningPreference] = Field(default_factory=list)
    constraints: list[PlanningConstraint] = Field(default_factory=list)
    desired_routines: list[str] = Field(default_factory=list)


class PlanningRecommendation(BaseModel):
    intention_id: str
    practice: str
    frequency: int = Field(ge=1, le=14)
    duration_minutes: int = Field(ge=15, le=240)
    spacing: str | None = None
    preferred_time: str | None = None
    priority: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)
    title: str | None = None
    rationale: str | None = None
    routine_impact: str | None = None
    evidence_summary: str | None = None


class EvidenceRecommendations(BaseModel):
    recommendations: list[PlanningRecommendation] = Field(default_factory=list)


class ScheduledBlock(BaseModel):
    date: str
    start: str
    end: str
    title: str
    type: str = "exploration"
    intention_id: str | None = None
    practice: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class GeneratedSchedule(BaseModel):
    fixed_blocks: list[ScheduledBlock] = Field(default_factory=list)
    exploration_blocks: list[ScheduledBlock] = Field(default_factory=list)


class ValidationViolation(BaseModel):
    block: str | None = None
    rule: str
    message: str


class ValidationResult(BaseModel):
    valid: bool
    violations: list[ValidationViolation] = Field(default_factory=list)


class RepairAttempt(BaseModel):
    strategy: str
    detail: str


class PlanningWeekRequest(BaseModel):
    user_intention: str
    wake_time: str
    sleep_time: str
    buffer_minutes: int = 60
    fixed_blocks: list[FixedBlock] = Field(default_factory=list)
    week_start: str | None = None


class PipelineMeta(BaseModel):
    intention_source: str
    recommendation_source: str
    evidence_hits: int
    exploration_blocks: int
    recommendations: int
    planning_model: str = "unknown"
    unique_exploration_titles: int = 0


class PipelineStageTrace(BaseModel):
    stage: str
    source: str
    model: str
    duration_ms: int
    input_summary: dict[str, Any] = Field(default_factory=dict)
    output_summary: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    evidence_id: str
    source: str
    domain: str
    category: str
    title: str
    text: str


class PlanningRunResponse(BaseModel):
    id: UUID
    status: PlanningStatus
    week_start: str
    week_end: str
    user_intention: str
    interpreted_intentions: InterpretedIntentions
    evidence_package_query: str
    evidence_items: list[EvidenceItem] = Field(default_factory=list)
    recommendations: list[PlanningRecommendation]
    generated_schedule: GeneratedSchedule
    validation_result: ValidationResult
    repair_history: list[RepairAttempt]
    pipeline_meta: PipelineMeta
    plan_summary: str | None = None
    pipeline_trace: list[PipelineStageTrace] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class AcceptPlanningResponse(BaseModel):
    status: PlanningStatus
    blocks_applied: int
    calendar_event_ids: list[str]
