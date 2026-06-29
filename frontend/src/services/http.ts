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
  try {
    const { data } = await refreshClient.post<AuthResponse>("/auth/refresh", {
      refresh_token: currentSession.refreshToken
    });
    const refreshedSession = toStoredSession(data);
    authStorage.set(refreshedSession);
    return refreshedSession;
  } catch {
    authStorage.clear();
    return null;
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
