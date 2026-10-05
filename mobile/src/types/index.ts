export type EventStatus = "pending" | "confirmed" | "skipped";

export interface AppEvent {
  id: string;
  title: string;
  scheduled_at: string;
  /** Present for one-time blocks; older routine rows may omit it. */
  duration_minutes?: number | null;
  status: EventStatus;
  memo_id: string | null;
}

export interface CurrentInsights {
  schema_version: "1.2";
  generated_at: string;
  source_files: string[];
  example: boolean;
  narrative: string;
  inference_bundle: InferenceBundle;
}

export interface BlockChange {
  action: "add" | "move" | "remove";
  block_id?: string;
  field?: string;
  old?: unknown;
  new?: unknown;
  title?: string;
  domain?: string;
  scheduled_at?: string;
  duration_minutes?: number;
}

export interface RoutineAdherence {
  planned: number;
  confirmed: number;
  adherence_rate: number;
  missed: string[];
}

export interface ReviewFinding {
  statement: string;
  evidence_paths: string[];
  confidence: "high" | "medium" | "low" | "none";
}

export interface ScientificSupport {
  claim: string;
  source_path: string;
  applicability: string;
}

/** A cited observation about how registered planning targets interacted. */
export interface GoalRelationship {
  statement: string;
  targets: Array<{ id?: string; priority_key?: string }>;
  evidence_paths: string[];
  confidence: "high" | "medium" | "low";
}

export interface InferenceBundle {
  schema_version: "1.2";
  routine_review: {
    summary: string;
    metrics: Record<string, unknown>;
    worked: ReviewFinding[];
    did_not_work: ReviewFinding[];
    experiments: string[];
  };
  goal_review: {
    registry_path: "../archive/long_term_goals.md";
    summary: string;
    assessments: Array<{
      id?: string;
      priority_key?: string;
      status: "evidenced" | "scheduled" | "partially_evidenced" | "not_tracked" | "at_risk" | "complete";
      evidence_paths: string[];
      confidence: "high" | "medium" | "low" | "none";
      findings: ReviewFinding[];
      recommendations: ScientificSupport[];
    }>;
  };
  future_plan_review: {
    summary: string;
    progress_updates: ReviewFinding[];
    new_additions: ReviewFinding[];
    unresolved_questions: string[];
    /** Additive schema-1.2 fields; absent in older saved reviews. */
    conflicts?: GoalRelationship[];
    facilitators?: GoalRelationship[];
  };
  life_pillar_review: {
    summary: string;
    groups: Array<{
      name: string;
      topics: Array<{
        name: string;
        status: "tracked" | "partially_tracked" | "not_tracked";
        evidence_paths: string[];
        confidence: "high" | "medium" | "low" | "none";
        findings: ReviewFinding[];
        recommendations: ScientificSupport[];
      }>;
    }>;
  };
}

export interface InferenceLog {
  id: string;
  inference_type: "routine" | "goals" | "future_plans";
  schema_version: string;
  status: "valid" | "invalid" | "failed";
  input_hash: string;
  output: Record<string, unknown> | null;
  citation_paths: string[];
  model: string | null;
  error_message: string | null;
  created_at: string;
}

export interface MemoUploadResponse {
  job_id: string;
  status: string;
}

export interface MemoStatusResponse {
  job_id: string;
  status: "queued" | "transcribing" | "done" | "error";
  error: string | null;
}

export interface MemoListItem {
  id: string;
  status: "queued" | "transcribing" | "done" | "error";
  event_title: string | null;
  created_at: string;
  /** False when a migrated memo preserved only its recording date. */
  recorded_at_known: boolean;
  transcript: string | null;
  error: string | null;
}

export interface LiveCalendarEvent {
  id: string;
  title: string;
  start: string;
  end: string;
  all_day: boolean;
}

// SQLite local types
export interface LocalEvent extends AppEvent {
  synced_at: string | null;
}

export interface LocalMemo {
  id: string;
  audio_path: string;
  event_id: string | null;
  event_title: string | null;
  synced_at: string | null;
}

export interface PlanningRecommendationItem {
  intention_id: string;
  practice: string;
  frequency: number;
  duration_minutes: number;
  spacing?: string | null;
  preferred_time?: string | null;
  priority: number;
  evidence_ids: string[];
  title?: string | null;
  rationale?: string | null;
  routine_impact?: string | null;
  evidence_summary?: string | null;
}

export interface PipelineMeta {
  intention_source: string;
  recommendation_source: string;
  evidence_hits: number;
  exploration_blocks: number;
  recommendations: number;
  planning_model?: string;
  unique_exploration_titles?: number;
}

export interface PipelineStageTrace {
  stage: string;
  source: string;
  model: string;
  duration_ms: number;
  input_summary?: Record<string, unknown>;
  output_summary?: Record<string, unknown>;
  notes?: string[];
}

export interface RoutineCalendarEvent {
  date: string;
  weekday?: string | null;
  day_theme?: string | null;
  start: string;
  end: string;
  title: string;
  category?: string | null;
  notes?: string | null;
}

export interface RoutineCalendar {
  source_markdown: string;
  version: string;
  week_start: string;
  week_end: string;
  timezone: string;
  event_count: number;
  events: RoutineCalendarEvent[];
}

export interface RoutineApplyResponse {
  batch_id: string;
  week_start: string;
  week_end: string;
  source_markdown: string;
  events_created: number;
  events_failed: number;
  events_existing?: number;
  calendar_event_ids: string[];
  events: Array<{
    date: string;
    start: string;
    end: string;
    title: string;
    google_event_id: string;
  }>;
  existing_events?: Array<{
    date: string;
    start: string;
    title: string;
  }>;
  errors: Array<{ date: string; title: string; error: string }>;
}

export interface ScheduledBlock {
  date: string;
  start: string;
  end: string;
  title: string;
  type: "fixed" | "exploration";
  intention_id?: string | null;
  practice?: string | null;
  evidence_ids?: string[];
}

export interface ValidationViolation {
  block?: string | null;
  rule: string;
  message: string;
}

export interface PlanningRun {
  id: string;
  status: string;
  week_start: string;
  week_end: string;
  user_intention: string;
  interpreted_intentions?: {
    intentions: Array<{
      id: string;
      theme: string;
      priority: string;
      desired_frequency?: number;
      preferred_duration_minutes?: number;
    }>;
    preferences?: Array<{ key: string; value: string }>;
    desired_routines?: string[];
  };
  recommendations: PlanningRecommendationItem[];
  generated_schedule: {
    fixed_blocks: ScheduledBlock[];
    exploration_blocks: ScheduledBlock[];
  };
  validation_result: {
    valid: boolean;
    violations: ValidationViolation[];
  };
  pipeline_meta?: PipelineMeta;
  plan_summary?: string | null;
  pipeline_trace?: PipelineStageTrace[];
  repair_history?: Array<{ strategy: string; detail: string }>;
  created_at: string;
  updated_at: string;
}
