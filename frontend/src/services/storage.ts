import type { StoredSession, User } from "../types";


const SESSION_STORAGE_KEY = "flexcrm.session";
const USER_STORAGE_KEY = "flexcrm.user";
const SIDEBAR_GROUPS_KEY = "flexcrm.sidebar-groups";

// In-memory mirror of the session + profile. This is the source of truth for the
// tab's lifetime, with localStorage as a best-effort durable backup. Some mobile
// contexts — notably in-app webviews (Instagram / WhatsApp) and browsers set to
// clear site data — persist localStorage unreliably, so a token written at login
// can be gone by the very next request (that's the "Missing bearer token" bug).
// Keeping it in memory keeps the session alive for the whole SPA visit even when
// localStorage doesn't stick; a hard reload falls back to whatever localStorage
// managed to save.
let sessionCache: StoredSession | null = null;
let sessionLoaded = false;
let userCache: User | null = null;
let userLoaded = false;

function readLocal<T>(key: string): T | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    try {
      window.localStorage.removeItem(key);
    } catch {
      /* ignore */
    }
    return null;
  }
}

function writeLocal(key: string, value: unknown): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage full / unavailable (private mode, webview) — memory still holds it */
  }
}

function removeLocal(key: string): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}

export const authStorage = {
  get(): StoredSession | null {
    if (!sessionLoaded) {
      sessionCache = readLocal<StoredSession>(SESSION_STORAGE_KEY);
      sessionLoaded = true;
    }
    return sessionCache;
  },

  set(session: StoredSession): void {
    sessionCache = session;
    sessionLoaded = true;
    writeLocal(SESSION_STORAGE_KEY, session);
  },

  /**
   * Last known user profile, cached so the app can restore instantly on reload
   * without blocking on /auth/profile. Permissions here are UI-gating only —
   * the server always re-enforces them — and are refreshed in the background.
   */
  getUser(): User | null {
    if (!userLoaded) {
      userCache = readLocal<User>(USER_STORAGE_KEY);
      userLoaded = true;
    }
    return userCache;
  },

  setUser(user: User): void {
    userCache = user;
    userLoaded = true;
    writeLocal(USER_STORAGE_KEY, user);
  },

  clear(): void {
    sessionCache = null;
    userCache = null;
    sessionLoaded = true;
    userLoaded = true;
    removeLocal(SESSION_STORAGE_KEY);
    removeLocal(USER_STORAGE_KEY);
  }
};


/**
 * Which sidebar groups (Finance / HR / Real Estate…) the user has expanded.
 * Purely a UI convenience — a missing/corrupt value just falls back to an empty
 * map (nothing pinned open; the active group still auto-opens at runtime).
 */
export const sidebarStorage = {
  get(): Record<string, boolean> {
    if (typeof window === "undefined") {
      return {};
    }
    const raw = window.localStorage.getItem(SIDEBAR_GROUPS_KEY);
    if (!raw) {
      return {};
    }
    try {
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? (parsed as Record<string, boolean>) : {};
    } catch {
      window.localStorage.removeItem(SIDEBAR_GROUPS_KEY);
      return {};
    }
  },

  set(groups: Record<string, boolean>): void {
    if (typeof window === "undefined") {
      return;
    }
    try {
      window.localStorage.setItem(SIDEBAR_GROUPS_KEY, JSON.stringify(groups));
    } catch {
      /* storage full / unavailable — expanded state is non-critical, ignore */
    }
  }
};
