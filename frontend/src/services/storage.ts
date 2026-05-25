import type { StoredSession } from "../types";


const SESSION_STORAGE_KEY = "flexcrm.session";

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

  clear(): void {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
  }
};
