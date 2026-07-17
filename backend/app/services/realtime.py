from __future__ import annotations

import contextvars
from collections import defaultdict, deque
from collections.abc import Iterable
from itertools import count
from typing import Any
from uuid import UUID

from fastapi import WebSocket

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


# Request-scoped org for org-scoped broadcasts. `get_current_user` sets this once
# per request; `broadcast()` reads it so an event only reaches sockets in the same
# org. Each FastAPI request runs in its own asyncio task with an isolated context,
# so concurrent requests from different orgs never bleed into each other.
_broadcast_org: contextvars.ContextVar[UUID | None] = contextvars.ContextVar(
    "broadcast_org", default=None
)


def set_broadcast_org(org_id: UUID | None) -> None:
    """Record the caller's org for the duration of this request's task."""
    _broadcast_org.set(org_id)


class RealtimeManager:
    """In-process pub/sub for `/ws/updates`, scoped per organization.

    Broadcasts fan out ONLY to sockets belonging to the emitting org (resolved
    from the request-scoped `_broadcast_org` contextvar), so no tenant ever sees
    another tenant's events. User-targeted sends (`broadcast_to_user`) already
    address a single user and stay as-is. The replay ring buffer is per-org too,
    so a reconnecting client only re-receives its own org's missed events.
    """

    def __init__(self) -> None:
        self._user_connections: dict[UUID, set[WebSocket]] = defaultdict(set)
        self._org_connections: dict[UUID, set[WebSocket]] = defaultdict(set)
        self._socket_org: dict[WebSocket, UUID] = {}
        self._event_id_seq = count(1)
        self._buffer_size = max(1, get_settings().websocket_event_buffer_size)
        self._org_buffers: dict[UUID, deque[dict[str, Any]]] = defaultdict(self._new_buffer)

    def _new_buffer(self) -> deque:
        return deque(maxlen=self._buffer_size)

    async def connect(
        self,
        websocket: WebSocket,
        user_id: UUID,
        org_id: UUID | None = None,
        last_event_id: int | None = None,
    ) -> None:
        await websocket.accept()
        # Replay the backlog BEFORE registering the socket for live broadcasts, so
        # a concurrent broadcast can't send_json on this socket (interleaved / out
        # of order) while replay is still in flight. A live event that arrives in
        # the brief replay window is still buffered and re-delivered on reconnect.
        if org_id is not None and last_event_id is not None:
            await self._replay(websocket, org_id, last_event_id)
        self._user_connections[user_id].add(websocket)
        if org_id is not None:
            self._org_connections[org_id].add(websocket)
            self._socket_org[websocket] = org_id

    def disconnect(self, websocket: WebSocket, user_id: UUID) -> None:
        conns = self._user_connections.get(user_id)
        if conns is not None:
            conns.discard(websocket)
            if not conns:
                self._user_connections.pop(user_id, None)
        self._detach_socket_org(websocket)

    async def broadcast(self, payload: dict, org_id: UUID | None = None) -> None:
        """Fan an event out to the emitting org's sockets only. `org_id` defaults
        to the request-scoped contextvar. With no org in context the event is
        dropped (never fanned out globally) — that global fan-out was the
        cross-tenant leak; the client refreshes to catch up."""
        org = org_id if org_id is not None else _broadcast_org.get()
        if org is None:
            logger.debug("realtime broadcast dropped (no org context): %s", payload.get("event"))
            return
        envelope = self._make_envelope(payload)
        self._org_buffers[org].append(envelope)
        await self._fan_out(self._org_connections.get(org, set()), envelope)

    async def broadcast_to_user(self, user_id: UUID, payload: dict) -> None:
        # User-targeted events are not buffered; only the user's live sockets get them.
        envelope = self._make_envelope(payload)
        await self._fan_out(self._user_connections.get(user_id, set()), envelope)

    def _make_envelope(self, payload: dict) -> dict[str, Any]:
        return {"id": next(self._event_id_seq), **payload}

    async def _replay(self, websocket: WebSocket, org_id: UUID, last_event_id: int) -> None:
        missed = [e for e in self._org_buffers.get(org_id, ()) if e["id"] > last_event_id]
        for event in missed:
            try:
                await websocket.send_json(event)
            except Exception:
                return

    async def _fan_out(self, sockets: Iterable[WebSocket], payload: dict) -> None:
        stale: list[WebSocket] = []
        for socket in list(sockets):
            try:
                await socket.send_json(payload)
            except Exception:
                stale.append(socket)
        for socket in stale:
            self._purge(socket)

    def _detach_socket_org(self, websocket: WebSocket) -> None:
        org = self._socket_org.pop(websocket, None)
        if org is None:
            return
        org_conns = self._org_connections.get(org)
        if org_conns is not None:
            org_conns.discard(websocket)
            if not org_conns:
                self._org_connections.pop(org, None)

    def _purge(self, socket: WebSocket) -> None:
        self._detach_socket_org(socket)
        for uid, conns in list(self._user_connections.items()):
            conns.discard(socket)
            if not conns:
                self._user_connections.pop(uid, None)


realtime_manager = RealtimeManager()
