import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type PropsWithChildren
} from "react";

import { authService } from "../services/auth";
import { authStorage } from "../services/storage";
import type { LoginPayload, RegisterPayload, StoredSession, User } from "../types";


interface AuthContextValue {
  user: User | null;
  session: StoredSession | null;
  loading: boolean;
  login: (payload: LoginPayload) => Promise<User>;
  register: (payload: RegisterPayload) => Promise<User>;
  logout: () => Promise<void>;
  refreshProfile: () => Promise<User | null>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);


export function AuthProvider({ children }: PropsWithChildren) {
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<StoredSession | null>(() => authStorage.get());
  const [loading, setLoading] = useState<boolean>(Boolean(authStorage.get()));

  const refreshProfile = useCallback(async () => {
    const activeSession = authStorage.get();
    if (!activeSession) {
      setUser(null);
      setSession(null);
      setLoading(false);
      return null;
    }

    try {
      const profile = await authService.profile();
      setUser(profile);
      setSession(activeSession);
      return profile;
    } catch (error) {
      authStorage.clear();
      setUser(null);
      setSession(null);
      throw error;
    } finally {
      setLoading(false);
    }
  }, []);

  const login = useCallback(async (payload: LoginPayload) => {
    const response = await authService.login(payload);
    const nextSession = authStorage.get();
    setUser(response.user);
    setSession(nextSession);
    return response.user;
  }, []);

  const register = useCallback(async (payload: RegisterPayload) => {
    const response = await authService.register(payload);
    const nextSession = authStorage.get();
    setUser(response.user);
    setSession(nextSession);
    return response.user;
  }, []);

  const logout = useCallback(async () => {
    try {
      await authService.logout();
    } finally {
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
      login,
      register,
      logout,
      refreshProfile
    }),
    [loading, login, logout, refreshProfile, register, session, user]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
