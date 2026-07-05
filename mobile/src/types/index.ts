export type EventStatus = "pending" | "confirmed" | "skipped";
export type PeriodType = "daily" | "weekly" | "monthly";
export type SentimentType = "positive" | "neutral" | "negative";

export interface AppEvent {
  id: string;
  title: string;
  scheduled_at: string;
  status: EventStatus;
  memo_id: string | null;
}

export interface DashboardMetric {
  metric_id: string;
  value: number;
  computed_for_date: string;
  metadata: Record<string, unknown>;
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

export interface ScheduleRecommendation {
  reasoning: string;
  blocks: BlockChange[];
}

export interface Insight {
  id: string;
  period_type: PeriodType;
  period_start: string;
  narrative: string;
  schedule_recommendation: ScheduleRecommendation | null;
  accepted: boolean;
  generated_at: string;
}

export interface MemoUploadResponse {
  job_id: string;
  status: string;
}

export interface MemoStatusResponse {
  job_id: string;
  status: "queued" | "transcribing" | "extracting" | "embedding" | "done" | "error";
  error: string | null;
}

// SQLite local types
export interface LocalEvent extends AppEvent {
  synced_at: string | null;
}

export interface LocalMemo {
  id: string;
  audio_path: string;
  transcript: string | null;
  features_json: string | null;
  synced_at: string | null;
}
