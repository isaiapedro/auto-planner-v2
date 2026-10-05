import { API_BASE_URLS, API_TOKEN } from "../config";
import { File } from "expo-file-system";
import type {
  AppEvent,
  CurrentInsights,
  LiveCalendarEvent,
  MemoListItem,
  MemoStatusResponse,
  MemoUploadResponse,
  RoutineApplyResponse,
  RoutineCalendar,
} from "../types";

const REQUEST_TIMEOUT_MS = 12_000;
// A routine can contain dozens of deliberate Google Calendar writes. Its
// response is synchronous, so it needs a longer bounded deadline than reads.
const ROUTINE_APPLY_TIMEOUT_MS = 120_000;
const UPLOAD_TIMEOUT_MS = 60_000;
const RETRY_DELAY_MS = 350;
const HEALTH_TIMEOUT_MS = 2_500;

let activeApiBaseUrl: string | null = null;

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

async function resolveApiBaseUrl(): Promise<string> {
  if (activeApiBaseUrl) return activeApiBaseUrl;
  for (const candidate of API_BASE_URLS) {
    try {
      const health = await fetchWithTimeout(`${candidate}/health`, { headers: { Accept: "application/json" } }, HEALTH_TIMEOUT_MS);
      if (health.ok) {
        activeApiBaseUrl = candidate;
        return candidate;
      }
    } catch {
      // Try the next configured LAN address. Health is read-only and unauthenticated.
    }
  }
  return API_BASE_URLS[0];
}

function clearUnreachableEndpoint(endpoint: string) {
  if (activeApiBaseUrl === endpoint) activeApiBaseUrl = null;
}

async function request<T>(path: string, init?: RequestInit, timeoutMs = REQUEST_TIMEOUT_MS): Promise<T> {
  if (!API_TOKEN) throw new Error("This app is missing its local API access token.");
  const method = (init?.method ?? "GET").toUpperCase();
  // GET has no server-side mutation, so retrying once after a transient
  // connection failure is safe. Mutating routes are deliberately never retried.
  const attempts = method === "GET" ? 2 : 1;
  const correlationId = requestId();
  let lastError: unknown;
  let lastEndpoint = API_BASE_URLS[0];
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const endpoint = await resolveApiBaseUrl();
    lastEndpoint = endpoint;
    try {
      const res = await fetchWithTimeout(`${endpoint}${path}`, {
        ...init,
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${API_TOKEN}`, "X-Request-ID": correlationId, ...init?.headers },
      }, timeoutMs);
      if (!res.ok) {
        const err = await res.text();
        throw new Error(`${res.status} ${path}: ${err}`);
      }
      return res.json() as Promise<T>;
    } catch (error) {
      lastError = error;
      // GET may select another healthy endpoint; writes are never replayed.
      clearUnreachableEndpoint(endpoint);
      if (attempt + 1 < attempts) await wait(RETRY_DELAY_MS);
    }
  }
  if (lastError instanceof Error && /^(4|5)\d\d /.test(lastError.message)) throw lastError;
  throw new Error(
    `Cannot reach API at ${lastEndpoint}${path}. Tried: ${API_BASE_URLS.join(", ")}. ` +
      "Use the same Wi-Fi as your PC and open the matching /health URL in the phone browser first."
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
  // Expo's current fetch implementation does not support React Native's
  // legacy `{ uri, name, type }` multipart part. Its File implements Blob,
  // allowing the native encoder to read the queued recording correctly.
  form.append("file", new File(audioUri));

  const params = new URLSearchParams();
  if (eventTitle) params.set("event_title", eventTitle);
  if (memoId) params.set("memo_id", memoId);
  const query = params.toString();
  // A client-generated UUID makes this POST idempotent: the server returns the
  // existing job if it already stored the recording. One retry covers a dropped
  // response after a successful durable write without creating a second memo.
  const attempts = memoId ? 2 : 1;
  const correlationId = requestId();
  let lastError: unknown;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const endpoint = await resolveApiBaseUrl();
    const url = `${endpoint}/memos/upload${query ? `?${query}` : ""}`;
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
      clearUnreachableEndpoint(endpoint);
      if (attempt + 1 < attempts) await wait(RETRY_DELAY_MS);
    }
  }
  throw lastError instanceof Error ? lastError : new Error("Upload failed.");
}

export async function getMemos(): Promise<MemoListItem[]> {
  // The authenticated Personal API returns the complete local history by
  // default. Do not add a client-side cap: the Memos tab is the mobile view of
  // the user's own `personal/planner/memos/` records.
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

/** Read current Google Calendar occurrences; this never changes calendar data. */
export async function getLiveCalendarEvents(start: string, end: string): Promise<LiveCalendarEvent[]> {
  const params = new URLSearchParams({ start, end });
  return request<LiveCalendarEvent[]>(`/events/live?${params.toString()}`);
}

// ── weekly routine ───────────────────────────────────────────────────────────

export async function getRoutineWeek() {
  return request<RoutineCalendar>("/routine/week");
}

export async function applyRoutineWeek() {
  return request<RoutineApplyResponse>("/routine/apply", { method: "POST" }, ROUTINE_APPLY_TIMEOUT_MS);
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

// ── sync ──────────────────────────────────────────────────────────────────────

export async function syncPull(): Promise<{ events: AppEvent[] }> {
  return request("/sync/pull");
}
