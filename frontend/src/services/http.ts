import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";

import type { AuthResponse, StoredSession } from "../types";
import { afterRefusal, beforeRenewal } from "../utils/sessionRenewal";
import { authStorage } from "./storage";


const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

// Cap requests so a hung/cold backend surfaces a friendly "timed out" error
// instead of an indefinite spinner. Registration provisioning is the slowest
// path (cold start + tenant migration), so allow generous headroom.
const REQUEST_TIMEOUT_MS = 60000;

export const apiClient = axios.create({
  baseURL: apiBaseUrl,
  timeout: REQUEST_TIMEOUT_MS,
  headers: {
    "Content-Type": "application/json"
  }
});

const refreshClient = axios.create({
  baseURL: apiBaseUrl,
  timeout: REQUEST_TIMEOUT_MS,
  headers: {
    "Content-Type": "application/json"
  }
});

interface RetriableRequestConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
  _retryCount?: number;
}

// Transient failures — a dropped/timed-out request, or a Cloud Run cold-start /
// rollout 5xx — carry no response (and no CORS header), so the browser reports
// them as "CORS" / network errors. Auto-retry these a few times with backoff so
// a brief blip never surfaces to the user. Only idempotent requests are retried.
// Retry budget is sized to outlast a Cloud Run cold start / deploy rollover
// (min-instances=0): 5 attempts at ~0.5/1/2/4/4s ≈ 11.5s total, so login and
// the dashboard ride through the window where a fresh, still-cold revision is
// dropping requests rather than surfacing "Unable to reach the server".
const MAX_TRANSIENT_RETRIES = 5;
const TRANSIENT_STATUS = new Set([502, 503, 504]);

function isTransientError(error: AxiosError): boolean {
  // No response → network drop, timeout (ECONNABORTED), DNS, or reset.
  if (!error.response) {
    return true;
  }
  return TRANSIENT_STATUS.has(error.response.status);
}

function isRetryableRequest(config: RetriableRequestConfig): boolean {
  const method = (config.method ?? "get").toLowerCase();
  if (method === "get" || method === "head" || method === "options") {
    return true;
  }
  // login/refresh are safe to replay — a retried login just mints a fresh token
  // pair. Writes that create rows (register, leads, …) are NOT retried, so a
  // request that may have reached the server can't be duplicated.
  const url = config.url ?? "";
  return method === "post" && (url.includes("/auth/login") || url.includes("/auth/refresh"));
}

function backoffDelay(attempt: number): number {
  // 0.5s, 1s, 2s, 4s, 4s (capped) + jitter. Capping keeps later attempts from
  // ballooning while still spanning a multi-second cold start.
  return Math.min(500 * 2 ** (attempt - 1), 4000) + Math.floor(Math.random() * 250);
}

// How a login renewal ended: a fresh session; "transient" (server unreachable / cold — the saved login is kept and
// the request just fails); or "ended" (the refresh token was refused — sign in again).
export type RenewalOutcome = { session: StoredSession } | { status: "transient" } | { status: "ended" };

let refreshPromise: Promise<RenewalOutcome> | null = null;

function toStoredSession(payload: AuthResponse): StoredSession {
  return {
    accessToken: payload.access_token,
    refreshToken: payload.refresh_token,
    accessTokenExpiresAt: payload.access_token_expires_at,
    refreshTokenExpiresAt: payload.refresh_token_expires_at
  };
}

async function renewOnce(mine: StoredSession): Promise<RenewalOutcome> {
  // Another tab may have renewed while this one waited for the lock: use its session (or its refresh token —
  // ours has been replaced) rather than presenting a replaced token. See utils/sessionRenewal.
  const before = beforeRenewal(mine, authStorage.getSaved(), Date.now());
  if (before.kind === "adopt") {
    authStorage.adopt(before.session);
    return { session: before.session };
  }
  const refreshToken = before.refreshToken;
  for (let attempt = 1; ; attempt += 1) {
    try {
      const { data } = await refreshClient.post<AuthResponse>("/auth/refresh", { refresh_token: refreshToken });
      const refreshedSession = toStoredSession(data);
      authStorage.set(refreshedSession);
      return { session: refreshedSession };
    } catch (error) {
      // Transient blip (no response / 5xx): retry with the same token — the server accepts a just-replaced token
      // for a few seconds, so a renewal whose reply was lost still succeeds. If retries run out, keep the saved
      // login: the user isn't signed out over a cold start, the request just fails.
      if (axios.isAxiosError(error) && isTransientError(error)) {
        if (attempt <= MAX_TRANSIENT_RETRIES) {
          await new Promise((resolve) => setTimeout(resolve, backoffDelay(attempt)));
          continue;
        }
        return { status: "transient" };
      }
      // Refused. If another tab renewed meanwhile, its saved session is the live one; otherwise the login ended —
      // and the saved copy is cleared only if it still holds the refused token.
      const after = afterRefusal(refreshToken, authStorage.getSaved());
      if (after.kind === "adopt") {
        authStorage.adopt(after.session);
        return { session: after.session };
      }
      authStorage.endIfCurrent(refreshToken, after.clearSaved);
      return { status: "ended" };
    }
  }
}

const RENEWAL_LOCK = "flexcrm-auth-refresh";

/**
 * Renew the login — one tab at a time (Web Locks), so tabs never race each other with the same refresh token; the
 * ones that waited pick up the winner's session in renewOnce. Without Web Locks (some in-app webviews) it renews
 * directly; the server's grace period and the shared-storage checks still keep the user signed in.
 */
async function refreshSession(currentSession: StoredSession): Promise<RenewalOutcome> {
  const locks = typeof navigator !== "undefined" ? navigator.locks : undefined;
  if (locks?.request) {
    try {
      return await locks.request(RENEWAL_LOCK, () => renewOnce(authStorage.get() ?? currentSession));
    } catch {
      /* lock manager unavailable (e.g. an opaque origin) — renew directly */
    }
  }
  return renewOnce(currentSession);
}

// Broadcast an unrecoverable auth failure so AuthContext can clear state and
// route the user to a clean "session ended, sign in again" screen — instead of
// leaving a logged-in-looking app whose writes fail with "Missing bearer token".
export const SESSION_EXPIRED_EVENT = "flexcrm:session-expired";

// Marks a request that failed because the login couldn't be renewed for a TRANSIENT reason (server unreachable /
// cold): the login is still good, so callers must not treat the 401 as "signed out".
const SESSION_KEPT = Symbol("flexcrm.session-kept");

export function isSessionKeptError(error: unknown): boolean {
  return Boolean(error && typeof error === "object" && (error as Record<symbol, unknown>)[SESSION_KEPT]);
}
export const SESSION_EXPIRED_FLAG = "flexcrm.session-expired";

function notifySessionExpired(): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.sessionStorage.setItem(SESSION_EXPIRED_FLAG, "1");
  } catch {
    /* ignore */
  }
  window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
}

/**
 * Proactively refresh the 15-minute access token when it's expired or close to
 * it (e.g. the tab regained focus after idling), so the user's next action
 * doesn't eat a 401 round-trip. Reuses the shared refresh promise so it never
 * races the response-interceptor refresh. No-op without a usable session.
 */
export async function proactiveRefresh(): Promise<void> {
  const session = authStorage.get();
  if (!session?.refreshToken || !session.accessToken) {
    return;
  }
  const expiresAt = Date.parse(session.accessTokenExpiresAt ?? "");
  if (Number.isNaN(expiresAt) || expiresAt - Date.now() > 90_000) {
    return; // still comfortably valid
  }
  await freshSession(90_000);
}

/**
 * The session, renewed first when its access token expires within `marginMs` — through the ONE shared renewal
 * (single-flight in this tab, one tab at a time across tabs). Everything that needs a fresh token uses this (the
 * HTTP layer, the realtime socket), so two parts of the app never renew with the same token. A login that really
 * ended fires the session-expired event; a transient failure keeps the login.
 */
export async function freshSession(marginMs: number): Promise<RenewalOutcome | { status: "signed-out" }> {
  const session = authStorage.get();
  if (!session?.refreshToken) {
    return { status: "signed-out" };
  }
  const expiresAt = Date.parse(session.accessTokenExpiresAt ?? "");
  if (session.accessToken && !Number.isNaN(expiresAt) && expiresAt - Date.now() > marginMs) {
    return { session };
  }
  refreshPromise ??= refreshSession(session).finally(() => {
    refreshPromise = null;
  });
  const outcome = await refreshPromise;
  if ("status" in outcome && outcome.status === "ended") {
    notifySessionExpired();
  }
  return outcome;
}

apiClient.interceptors.request.use((config) => {
  const session = authStorage.get();
  if (session?.accessToken) {
    config.headers = config.headers ?? {};
    config.headers.Authorization = `Bearer ${session.accessToken}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as RetriableRequestConfig | undefined;

    // Retry transient failures (cold-start/rollout drops, timeouts, 5xx) on
    // idempotent requests before doing anything else. By the time the backoff
    // elapses, the warm instance answers — the user never sees the blip.
    if (originalRequest && isTransientError(error) && isRetryableRequest(originalRequest)) {
      const attempt = (originalRequest._retryCount ?? 0) + 1;
      if (attempt <= MAX_TRANSIENT_RETRIES) {
        originalRequest._retryCount = attempt;
        await new Promise((resolve) => setTimeout(resolve, backoffDelay(attempt)));
        return apiClient(originalRequest);
      }
    }

    const responseStatus = error.response?.status;

    if (
      responseStatus !== 401 ||
      !originalRequest ||
      originalRequest._retry ||
      originalRequest.url?.includes("/auth/login") ||
      originalRequest.url?.includes("/auth/register") ||
      originalRequest.url?.includes("/auth/refresh")
    ) {
      return Promise.reject(error);
    }

    let session = authStorage.get();
    if (!session?.refreshToken) {
      // This tab has none, but another tab may have saved a login since — use it.
      const saved = authStorage.getSaved();
      if (saved?.refreshToken) {
        authStorage.adopt(saved);
        session = saved;
      }
    }
    if (!session?.refreshToken) {
      // No way to recover (session gone / no refresh token) — clear and send the
      // app to a clean re-login rather than surfacing a raw auth error.
      authStorage.clear();
      notifySessionExpired();
      return Promise.reject(error);
    }

    originalRequest._retry = true;
    refreshPromise ??= refreshSession(session).finally(() => {
      refreshPromise = null;
    });

    const outcome = await refreshPromise;
    if (!("session" in outcome)) {
      // "ended": the refresh token was refused — session over, sign in again. "transient": the server couldn't be
      // reached even after retries — keep the login and let this request fail like any network error.
      if (outcome.status === "ended") notifySessionExpired();
      else (error as unknown as Record<symbol, unknown>)[SESSION_KEPT] = true;
      return Promise.reject(error);
    }

    originalRequest.headers = originalRequest.headers ?? {};
    originalRequest.headers.Authorization = `Bearer ${outcome.session.accessToken}`;
    return apiClient(originalRequest);
  }
);
