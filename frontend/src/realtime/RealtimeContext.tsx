import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PropsWithChildren
} from "react";

import { authService } from "../services/auth";
import { authStorage } from "../services/storage";
import type { StoredSession } from "../types";


export type RealtimeStatus = "idle" | "connecting" | "online" | "offline";

export interface RealtimeEnvelope {
  id: number;
  event: string;
  payload: unknown;
}

type Listener = (event: RealtimeEnvelope) => void;

interface RealtimeContextValue {
  status: RealtimeStatus;
  lastEventId: number | null;
  subscribe: (listener: Listener) => () => void;
}


const RealtimeContext = createContext<RealtimeContextValue | null>(null);

const RECONNECT_DELAYS_MS = [1000, 2000, 4000, 8000, 15000];

// Refresh the access token if it's within this window of expiring. The WS
// upgrade carries the token as a query-string param; the browser sees only an
// opaque close on 403, so we can't reactively refresh on a rejected handshake
// the way the axios interceptor does for HTTP 401. We must be proactive.
const REFRESH_BEFORE_EXPIRY_MS = 60_000;


async function ensureFreshSession(): Promise<StoredSession | null> {
  const session = authStorage.get();
  if (!session) {
    return null;
  }

  const expiresAt = new Date(session.accessTokenExpiresAt).getTime();
  if (!Number.isNaN(expiresAt) && expiresAt - Date.now() > REFRESH_BEFORE_EXPIRY_MS) {
    return session;
  }

  try {
    await authService.refresh({ refresh_token: session.refreshToken });
    return authStorage.get();
  } catch {
    // Refresh token itself is invalid/expired — the user is effectively logged
    // out. Clear local state so the next protected HTTP call redirects to login.
    authStorage.clear();
    return null;
  }
}


function toWsBase(input: string): string | null {
  const trimmed = input.trim();
  if (!trimmed) return null;

  if (trimmed.startsWith("ws://") || trimmed.startsWith("wss://")) {
    return trimmed.replace(/\/$/, "");
  }

  if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
    try {
      const url = new URL(trimmed);
      const protocol = url.protocol === "https:" ? "wss:" : "ws:";
      return `${protocol}//${url.host}${url.pathname.replace(/\/$/, "")}`;
    } catch {
      return null;
    }
  }

  // Relative path (e.g. "/api/v1") — derive scheme + host from window.location.
  if (typeof window === "undefined") return null;
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const path = (trimmed.startsWith("/") ? trimmed : `/${trimmed}`).replace(/\/$/, "");
  return `${protocol}//${window.location.host}${path}`;
}


function resolveWebsocketUrl(token: string, lastEventId: number | null): string | null {
  const explicit = import.meta.env.VITE_WS_BASE_URL;
  const apiBase = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

  const base =
    (typeof explicit === "string" && explicit.trim() ? toWsBase(explicit) : null) ??
    toWsBase(apiBase);
  if (!base) return null;

  const params = new URLSearchParams({ token });
  if (lastEventId !== null) {
    params.set("last_event_id", String(lastEventId));
  }
  return `${base}/ws/updates?${params.toString()}`;
}


export function RealtimeProvider({ children }: PropsWithChildren) {
  const [status, setStatus] = useState<RealtimeStatus>("idle");
  const [lastEventId, setLastEventId] = useState<number | null>(null);

  // Refs keep reconnection logic free of stale closures. State drives renders;
  // refs drive the connection lifecycle.
  const listenersRef = useRef<Set<Listener>>(new Set());
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimerRef = useRef<number | null>(null);
  const closedByUsRef = useRef(false);
  const lastEventIdRef = useRef<number | null>(null);

  useEffect(() => {
    lastEventIdRef.current = lastEventId;
  }, [lastEventId]);

  const dispatch = useCallback((event: RealtimeEnvelope) => {
    listenersRef.current.forEach((listener) => {
      try {
        listener(event);
      } catch (error) {
        // eslint-disable-next-line no-console
        console.error("[realtime] listener error", error);
      }
    });
  }, []);

  const connect = useCallback(async () => {
    if (closedByUsRef.current) {
      return;
    }
    setStatus("connecting");

    const session = await ensureFreshSession();
    if (closedByUsRef.current) {
      // Provider unmounted during the refresh round-trip.
      return;
    }
    if (!session?.accessToken) {
      setStatus("idle");
      return;
    }

    const url = resolveWebsocketUrl(session.accessToken, lastEventIdRef.current);
    if (!url) {
      setStatus("offline");
      return;
    }

    let socket: WebSocket;
    try {
      socket = new WebSocket(url);
    } catch {
      setStatus("offline");
      return;
    }
    socketRef.current = socket;

    socket.onopen = () => {
      reconnectAttemptsRef.current = 0;
      setStatus("online");
    };

    socket.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data) as RealtimeEnvelope;
        if (typeof parsed.id === "number") {
          const next =
            lastEventIdRef.current === null || parsed.id > lastEventIdRef.current
              ? parsed.id
              : lastEventIdRef.current;
          lastEventIdRef.current = next;
          setLastEventId(next);
        }
        dispatch(parsed);
      } catch {
        // Server only sends JSON envelopes; ignore malformed frames.
      }
    };

    socket.onerror = () => {
      // The close handler does the recovery work.
    };

    socket.onclose = () => {
      socketRef.current = null;
      if (closedByUsRef.current) {
        return;
      }
      setStatus("offline");
      const attempt = reconnectAttemptsRef.current;
      const delay = RECONNECT_DELAYS_MS[Math.min(attempt, RECONNECT_DELAYS_MS.length - 1)];
      reconnectAttemptsRef.current = attempt + 1;
      reconnectTimerRef.current = window.setTimeout(() => {
        reconnectTimerRef.current = null;
        void connect();
      }, delay);
    };
  }, [dispatch]);

  useEffect(() => {
    closedByUsRef.current = false;
    void connect();
    return () => {
      closedByUsRef.current = true;
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
    };
  }, [connect]);

  const subscribe = useCallback((listener: Listener) => {
    listenersRef.current.add(listener);
    return () => {
      listenersRef.current.delete(listener);
    };
  }, []);

  const value = useMemo<RealtimeContextValue>(
    () => ({ status, lastEventId, subscribe }),
    [status, lastEventId, subscribe]
  );

  return <RealtimeContext.Provider value={value}>{children}</RealtimeContext.Provider>;
}


export function useRealtime(): RealtimeContextValue {
  const context = useContext(RealtimeContext);
  if (!context) {
    throw new Error("useRealtime must be used within RealtimeProvider");
  }
  return context;
}


export function useRealtimeEvent(handler: (event: RealtimeEnvelope) => void): void {
  const { subscribe } = useRealtime();
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  useEffect(() => {
    return subscribe((event) => handlerRef.current(event));
  }, [subscribe]);
}
