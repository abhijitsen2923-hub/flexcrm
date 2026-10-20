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
   * The session as last saved for every tab (localStorage), not this tab's memory copy — to see whether another
   * tab renewed the login meanwhile. null when nothing is saved or storage is unavailable.
   */
  getSaved(): StoredSession | null {
    return readLocal<StoredSession>(SESSION_STORAGE_KEY);
  },

  /** Use a session another tab saved (already in storage — nothing to write). */
  adopt(session: StoredSession): void {
    sessionCache = session;
    sessionLoaded = true;
  },

  /**
   * This tab's login ended (its refresh token was refused): forget it here, and clear the saved copy only when it
   * still holds that token — another tab may have saved a newer login, which must survive.
   */
  endIfCurrent(refusedRefreshToken: string, clearSaved: boolean): void {
    if (sessionCache?.refreshToken === refusedRefreshToken) {
      sessionCache = null;
      sessionLoaded = true;
    }
    if (clearSaved) {
      removeLocal(SESSION_STORAGE_KEY);
      removeLocal(USER_STORAGE_KEY);
    }
  },

  /** Drop this tab's copy only (the saved one is handled by whoever decided the login ended). */
  forgetInThisTab(): void {
    sessionCache = null;
    userCache = null;
    sessionLoaded = true;
    userLoaded = true;
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


// Tabs share one saved login: when another tab renews it (each renewal replaces the refresh token) or signs out,
// this tab picks that up at once instead of later trying a replaced token and getting signed out. (`storage` events
// fire only in the OTHER tabs.)
if (typeof window !== "undefined") {
  window.addEventListener("storage", (event) => {
    if (event.storageArea !== window.localStorage || event.key !== SESSION_STORAGE_KEY) return;
    try {
      sessionCache = event.newValue ? (JSON.parse(event.newValue) as StoredSession) : null;
      sessionLoaded = true;
    } catch {
      /* a corrupt value — keep what this tab has */
    }
  });
}


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
