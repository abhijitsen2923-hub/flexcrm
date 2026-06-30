import type { StoredSession, User } from "../types";


const SESSION_STORAGE_KEY = "flexcrm.session";
const USER_STORAGE_KEY = "flexcrm.user";

export const authStorage = {
  get(): StoredSession | null {
    if (typeof window === "undefined") {
      return null;
    }
    const raw = window.localStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) {
      return null;
    }

    try {
      return JSON.parse(raw) as StoredSession;
    } catch {
      window.localStorage.removeItem(SESSION_STORAGE_KEY);
      return null;
    }
  },

  set(session: StoredSession): void {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
  },

  /**
   * Last known user profile, cached so the app can restore instantly on reload
   * without blocking on /auth/profile. Permissions here are UI-gating only —
   * the server always re-enforces them — and are refreshed in the background.
   */
  getUser(): User | null {
    if (typeof window === "undefined") {
      return null;
    }
    const raw = window.localStorage.getItem(USER_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    try {
      return JSON.parse(raw) as User;
    } catch {
      window.localStorage.removeItem(USER_STORAGE_KEY);
      return null;
    }
  },

  setUser(user: User): void {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
  },

  clear(): void {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
    window.localStorage.removeItem(USER_STORAGE_KEY);
  }
};
