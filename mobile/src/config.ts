export const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000";

export const POLL_INTERVAL_MS = 2000;   // status polling for memo upload
export const POLL_MAX_ATTEMPTS = 60;    // 2 min timeout
