import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";

import type { AuthResponse, StoredSession } from "../types";
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

let refreshPromise: Promise<StoredSession | null> | null = null;

function toStoredSession(payload: AuthResponse): StoredSession {
  return {
    accessToken: payload.access_token,
    refreshToken: payload.refresh_token,
    accessTokenExpiresAt: payload.access_token_expires_at,
    refreshTokenExpiresAt: payload.refresh_token_expires_at
  };
}

async function refreshSession(currentSession: StoredSession): Promise<StoredSession | null> {
  for (let attempt = 1; ; attempt += 1) {
    try {
      const { data } = await refreshClient.post<AuthResponse>("/auth/refresh", {
        refresh_token: currentSession.refreshToken
      });
      const refreshedSession = toStoredSession(data);
      authStorage.set(refreshedSession);
      return refreshedSession;
    } catch (error) {
      // Transient blip (no response / 5xx): retry, and if retries are exhausted
      // keep the stored session so the user isn't logged out over a cold start.
      if (axios.isAxiosError(error) && isTransientError(error)) {
        if (attempt <= MAX_TRANSIENT_RETRIES) {
          await new Promise((resolve) => setTimeout(resolve, backoffDelay(attempt)));
          continue;
        }
        return null;
      }
      // Genuine auth failure (expired/invalid refresh token) → clear and log out.
      authStorage.clear();
      return null;
    }
  }
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

    const session = authStorage.get();
    if (!session?.refreshToken) {
      authStorage.clear();
      return Promise.reject(error);
    }

    originalRequest._retry = true;
    refreshPromise ??= refreshSession(session).finally(() => {
      refreshPromise = null;
    });

    const refreshedSession = await refreshPromise;
    if (!refreshedSession?.accessToken) {
      return Promise.reject(error);
    }

    originalRequest.headers = originalRequest.headers ?? {};
    originalRequest.headers.Authorization = `Bearer ${refreshedSession.accessToken}`;
    return apiClient(originalRequest);
  }
);
