from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable
from itertools import count
from typing import Any
from uuid import UUID

from fastapi import WebSocket

from app.core.config import get_settings


class RealtimeManager:
    """In-process broadcast hub for the `/ws/updates` endpoint.

    Each outgoing event is tagged with a monotonically increasing `id`. The
    manager keeps the last N envelopes in a ring buffer so a client can pass
    `last_event_id` on reconnect and receive everything it missed (within the
    buffer window). The buffer is per-process — for multi-worker deployments
    a Redis-backed stream would be needed; that's intentionally deferred.
    """

    def __init__(self) -> None:
        self._connections: dict[UUID, set[WebSocket]] = defaultdict(set)
        self._broadcast_connections: set[WebSocket] = set()
        self._event_id_seq = count(1)
        buffer_size = max(1, get_settings().websocket_event_buffer_size)
        self._event_buffer: deque[dict[str, Any]] = deque(maxlen=buffer_size)

    async def connect(
        self,
        websocket: WebSocket,
        user_id: UUID,
        last_event_id: int | None = None,
    ) -> None:
        await websocket.accept()
        self._connections[user_id].add(websocket)
        self._broadcast_connections.add(websocket)
        if last_event_id is not None:
            await self._replay(websocket, last_event_id)

    def disconnect(self, websocket: WebSocket, user_id: UUID) -> None:
        if user_id in self._connections:
            self._connections[user_id].discard(websocket)
            if not self._connections[user_id]:
                self._connections.pop(user_id, None)
        self._broadcast_connections.discard(websocket)

    async def broadcast(self, payload: dict) -> None:
        envelope = self._make_envelope(payload)
        self._event_buffer.append(envelope)
        await self._fan_out(self._broadcast_connections, envelope)

    async def broadcast_to_user(self, user_id: UUID, payload: dict) -> None:
        envelope = self._make_envelope(payload)
        # User-targeted events are not added to the broadcast buffer; only the
        # currently-connected sockets for that user receive them.
        await self._fan_out(self._connections.get(user_id, set()), envelope)

    def _make_envelope(self, payload: dict) -> dict[str, Any]:
        return {"id": next(self._event_id_seq), **payload}

    async def _replay(self, websocket: WebSocket, last_event_id: int) -> None:
        missed = [event for event in self._event_buffer if event["id"] > last_event_id]
        for event in missed:
            try:
                await websocket.send_json(event)
            except Exception:
                # If replay fails the socket will be cleaned up on next fan-out.
                return

    async def _fan_out(self, sockets: Iterable[WebSocket], payload: dict) -> None:
        stale: list[WebSocket] = []
        for socket in list(sockets):
            try:
                await socket.send_json(payload)
            except Exception:
                stale.append(socket)
        for socket in stale:
            self._broadcast_connections.discard(socket)
            for user_id, connections in list(self._connections.items()):
                connections.discard(socket)
                if not connections:
                    self._connections.pop(user_id, None)


realtime_manager = RealtimeManager()
