import type { AuthResponse, LoginPayload, RefreshPayload, RegisterPayload, StoredSession, User } from "../types";
import { apiClient } from "./http";
import { authStorage } from "./storage";


function toStoredSession(payload: AuthResponse): StoredSession {
  return {
    accessToken: payload.access_token,
    refreshToken: payload.refresh_token,
    accessTokenExpiresAt: payload.access_token_expires_at,
    refreshTokenExpiresAt: payload.refresh_token_expires_at
  };
}

export const authService = {
  async register(payload: RegisterPayload): Promise<AuthResponse> {
    const { data } = await apiClient.post<AuthResponse>("/auth/register", payload);
    authStorage.set(toStoredSession(data));
    return data;
  },

  async login(payload: LoginPayload): Promise<AuthResponse> {
    const { data } = await apiClient.post<AuthResponse>("/auth/login", payload);
    authStorage.set(toStoredSession(data));
    return data;
  },

  async refresh(payload: RefreshPayload): Promise<AuthResponse> {
    const { data } = await apiClient.post<AuthResponse>("/auth/refresh", payload);
    authStorage.set(toStoredSession(data));
    return data;
  },

  async logout(): Promise<void> {
    const session = authStorage.get();
    try {
      if (session?.refreshToken) {
        await apiClient.post("/auth/logout", { refresh_token: session.refreshToken });
      }
    } finally {
      authStorage.clear();
    }
  },

  async profile(): Promise<User> {
    const { data } = await apiClient.get<User>("/auth/profile");
    return data;
  }
};
