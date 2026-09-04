import axios from "axios";
import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type PropsWithChildren
} from "react";

import { clearResourceCache } from "../hooks/resourceCache";
import { authService } from "../services/auth";
import { authStorage } from "../services/storage";
import type { LoginPayload, RegisterPayload, StoredSession, User } from "../types";


interface AuthContextValue {
  user: User | null;
  session: StoredSession | null;
  loading: boolean;
  /** True when we have a session but profile restore failed transiently (offline/cold). */
  restoreFailed: boolean;
  login: (payload: LoginPayload) => Promise<User>;
  register: (payload: RegisterPayload) => Promise<User>;
  logout: () => Promise<void>;
  refreshProfile: () => Promise<User | null>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);


export function AuthProvider({ children }: PropsWithChildren) {
  // Restore optimistically from the cached profile so a returning user sees the
  // app immediately, even while /auth/profile is in flight (or the backend is
  // cold-starting). We only block on the restore screen when we have a session
  // token but no cached profile yet (rare — e.g. cleared cache).
  const [user, setUser] = useState<User | null>(() => authStorage.getUser());
  const [session, setSession] = useState<StoredSession | null>(() => authStorage.get());
  const [loading, setLoading] = useState<boolean>(
    () => Boolean(authStorage.get()) && !authStorage.getUser()
  );
  const [restoreFailed, setRestoreFailed] = useState<boolean>(false);

  const refreshProfile = useCallback(async () => {
    const activeSession = authStorage.get();
    if (!activeSession) {
      authStorage.clear();
      setUser(null);
      setSession(null);
      setRestoreFailed(false);
      setLoading(false);
      return null;
    }

    setRestoreFailed(false);
    try {
      const profile = await authService.profile();
      authStorage.setUser(profile);
      setUser(profile);
      setSession(activeSession);
      return profile;
    } catch (error) {
      // Only sign the user out when the session is genuinely invalid: the http
      // interceptor clears storage after a failed token refresh, or the server
      // returns 401/403. Transient failures (cold start, timeout, network, 5xx)
      // must NOT log the user out — keep the cached profile and let a later
      // refresh hydrate it.
      const status = axios.isAxiosError(error) ? error.response?.status : undefined;
      const sessionInvalid = !authStorage.get() || status === 401 || status === 403;
      if (sessionInvalid) {
        authStorage.clear();
        clearResourceCache();
        setUser(null);
        setSession(null);
      } else {
        const cached = authStorage.getUser();
        setUser(cached);
        // No cached profile to fall back on → let ProtectedRoute offer a retry
        // instead of bouncing a still-valid session to the login screen.
        setRestoreFailed(!cached);
      }
      return authStorage.getUser();
    } finally {
      setLoading(false);
    }
  }, []);

  const login = useCallback(async (payload: LoginPayload) => {
    const response = await authService.login(payload);
    const nextSession = authStorage.get();
    authStorage.setUser(response.user);
    setUser(response.user);
    setSession(nextSession);
    return response.user;
  }, []);

  const register = useCallback(async (payload: RegisterPayload) => {
    const response = await authService.register(payload);
    const nextSession = authStorage.get();
    authStorage.setUser(response.user);
    setUser(response.user);
    setSession(nextSession);
    return response.user;
  }, []);

  const logout = useCallback(async () => {
    try {
      await authService.logout();
    } finally {
      clearResourceCache();
      setUser(null);
      setSession(null);
    }
  }, []);

  useEffect(() => {
    void refreshProfile();
  }, [refreshProfile]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      session,
      loading,
      restoreFailed,
      login,
      register,
      logout,
      refreshProfile
    }),
    [loading, restoreFailed, login, logout, refreshProfile, register, session, user]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
