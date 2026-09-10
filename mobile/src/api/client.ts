import { API_BASE_URL, API_TOKEN } from "../config";
import type {
  AppEvent,
  AccountProposal,
  AccountProposalList,
  AccountTriageRun,
  CurrentInsights,
  Insight,
  MemoListItem,
  MemoStatusResponse,
  MemoUploadResponse,
  RoutineApplyResponse,
  RoutineCalendar,
} from "../types";

const REQUEST_TIMEOUT_MS = 12_000;
const UPLOAD_TIMEOUT_MS = 60_000;
const RETRY_DELAY_MS = 350;

function requestId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function wait(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchWithTimeout(url: string, init: RequestInit, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (error) {
    if (controller.signal.aborted) throw new Error("The request timed out. Please try again.");
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_TOKEN) throw new Error("This app is missing its local API access token.");
  const method = (init?.method ?? "GET").toUpperCase();
  // GET has no server-side mutation, so retrying once after a transient
  // connection failure is safe. Mutating routes are deliberately never retried.
  const attempts = method === "GET" ? 2 : 1;
  const correlationId = requestId();
  let lastError: unknown;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const res = await fetchWithTimeout(`${API_BASE_URL}${path}`, {
        ...init,
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${API_TOKEN}`, "X-Request-ID": correlationId, ...init?.headers },
      }, REQUEST_TIMEOUT_MS);
      if (!res.ok) {
        const err = await res.text();
        throw new Error(`${res.status} ${path}: ${err}`);
      }
      return res.json() as Promise<T>;
    } catch (error) {
      lastError = error;
      if (attempt + 1 < attempts) await wait(RETRY_DELAY_MS);
    }
  }
  if (lastError instanceof Error && /^(4|5)\d\d /.test(lastError.message)) throw lastError;
  throw new Error(
    `Cannot reach API at ${API_BASE_URL}${path}. ` +
      "Use the same Wi-Fi as your PC and open /health in the phone browser first."
  );
}

// ── memos ─────────────────────────────────────────────────────────────────────

export async function uploadMemo(
  audioUri: string,
  eventTitle?: string,
  memoId?: string
): Promise<MemoUploadResponse> {
  if (!API_TOKEN) throw new Error("This app is missing its local API access token.");
  const form = new FormData();
  form.append("file", { uri: audioUri, name: "memo.m4a", type: "audio/mp4" } as any);

  const params = new URLSearchParams();
  if (eventTitle) params.set("event_title", eventTitle);
  if (memoId) params.set("memo_id", memoId);
  const query = params.toString();
  const url = `${API_BASE_URL}/memos/upload${query ? `?${query}` : ""}`;

  // A client-generated UUID makes this POST idempotent: the server returns the
  // existing job if it already stored the recording. One retry covers a dropped
  // response after a successful durable write without creating a second memo.
  const attempts = memoId ? 2 : 1;
  const correlationId = requestId();
  let lastError: unknown;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const res = await fetchWithTimeout(url, {
        method: "POST",
        headers: { Authorization: `Bearer ${API_TOKEN}`, "X-Request-ID": correlationId },
        body: form,
      }, UPLOAD_TIMEOUT_MS);
      if (!res.ok) throw new Error(`Upload failed: ${await res.text()}`);
      return res.json();
    } catch (error) {
      lastError = error;
      if (attempt + 1 < attempts) await wait(RETRY_DELAY_MS);
    }
  }
  throw lastError instanceof Error ? lastError : new Error("Upload failed.");
}

export async function getMemos(): Promise<MemoListItem[]> {
  return request<MemoListItem[]>("/memos");
}

export async function getMemoStatus(jobId: string): Promise<MemoStatusResponse> {
  return request<MemoStatusResponse>(`/memos/${jobId}/status`);
}

// ── events ────────────────────────────────────────────────────────────────────

export async function confirmEvent(
  eventId: string,
  confirmed: boolean,
  memoId?: string
): Promise<AppEvent> {
  return request<AppEvent>(`/events/${eventId}/confirm`, {
    method: "POST",
    body: JSON.stringify({ confirmed, memo_id: memoId ?? null }),
  });
}

export async function createCalendarBlock(body: {
  title: string;
  scheduled_at: string;
  duration_minutes: number;
}): Promise<AppEvent> {
  return request<AppEvent>("/events", { method: "POST", body: JSON.stringify(body) });
}

/** Saved Planner events for a half-open calendar-date range [start, end). */
export async function getEventsForRange(start: string, end: string): Promise<AppEvent[]> {
  const params = new URLSearchParams({ start, end });
  return request<AppEvent[]>(`/events?${params.toString()}`);
}

// ── weekly routine ───────────────────────────────────────────────────────────

export async function getRoutineWeek() {
  return request<RoutineCalendar>("/routine/week");
}

export async function applyRoutineWeek() {
  return request<RoutineApplyResponse>("/routine/apply", { method: "POST" });
}

export async function syncRoutineEventsLocal() {
  return request<RoutineApplyResponse>("/routine/sync-local", { method: "POST" });
}

// ── goals ─────────────────────────────────────────────────────────────────────

export async function createGoal(goal: unknown) {
  return request("/goals", { method: "POST", body: JSON.stringify(goal) });
}

// ── insights ──────────────────────────────────────────────────────────────────

export async function getCurrentInsights(): Promise<CurrentInsights> {
  return request("/insights/current");
}

// ── account inbox ────────────────────────────────────────────────────────────

/** Proposals are intentionally metadata-only; source evidence stays server-side. */
export async function getAccountProposals(): Promise<AccountProposalList> {
  const result = await request<AccountProposalList | AccountProposal[]>("/account/proposals?status=proposed");
  return Array.isArray(result) ? { proposals: result } : { proposals: result.proposals ?? [], generated_at: result.generated_at };
}

/**
 * Account runs are intentionally rendered as aggregate operational metadata.
 * The server may add safe model/fallback fields over time; transcript evidence
 * and memo references remain opaque to the client.
 */
export async function getAccountRuns(): Promise<AccountTriageRun[]> {
  const result = await request<AccountTriageRun[] | { runs?: AccountTriageRun[] }>("/account/runs");
  const rows = Array.isArray(result) ? result : result.runs ?? [];
  return rows.map((row) => {
    // Accept additive backend naming while keeping the screen metadata-only.
    // Raw failure details deliberately never cross this normalization boundary.
    const candidate = row as AccountTriageRun & Record<string, unknown>;
    return {
      ...row,
      proposal_ids: Array.isArray(row.proposal_ids) ? row.proposal_ids : [],
      memo_ids: Array.isArray(row.memo_ids) ? row.memo_ids : [],
      model_label: typeof candidate.model_label === "string" ? candidate.model_label : typeof candidate.model_id === "string" ? candidate.model_id : typeof candidate.model === "string" ? candidate.model : undefined,
      fallback_used: typeof candidate.fallback_used === "boolean" ? candidate.fallback_used : typeof candidate.used_fallback === "boolean" ? candidate.used_fallback : row.status === "needs_manual_review",
      completed_at: typeof candidate.completed_at === "string" ? candidate.completed_at : typeof candidate.finished_at === "string" ? candidate.finished_at : undefined,
    };
  });
}

/** Fetch a resolved outcome list without asking the API to expose evidence. */
export async function getAccountProposalsByStatus(status: "accepted" | "dismissed"): Promise<AccountProposal[]> {
  const result = await request<AccountProposalList | AccountProposal[]>(`/account/proposals?status=${status}`);
  return Array.isArray(result) ? result : result.proposals ?? [];
}

export async function acceptAccountProposal(proposalId: string): Promise<AccountProposal> {
  return request<AccountProposal>(`/account/proposals/${encodeURIComponent(proposalId)}/accept`, { method: "POST" });
}

export async function dismissAccountProposal(proposalId: string): Promise<AccountProposal> {
  return request<AccountProposal>(`/account/proposals/${encodeURIComponent(proposalId)}/dismiss`, { method: "POST" });
}

/** Starts an explicit, metadata-only account review for completed memo IDs. */
export async function runAccountTriage(memoIds: string[], instruction?: string): Promise<AccountTriageRun> {
  return request<AccountTriageRun>("/account/triage", {
    method: "POST",
    body: JSON.stringify({ memo_ids: memoIds, instruction: instruction?.trim() || undefined }),
  });
}

// ── sync ──────────────────────────────────────────────────────────────────────

export async function syncPull(): Promise<{ events: AppEvent[]; latest_insight: Insight | null }> {
  return request("/sync/pull");
}
