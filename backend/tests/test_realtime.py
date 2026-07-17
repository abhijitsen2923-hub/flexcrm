from uuid import uuid4

import pytest

from app.api.v1.endpoints.websocket import _parse_last_event_id
from app.services.realtime import RealtimeManager


class FakeWebSocket:
    """Minimal stand-in for starlette.WebSocket — captures sent envelopes."""

    def __init__(self, *, fail: bool = False) -> None:
        self.accepted = False
        self.sent: list[dict] = []
        self.fail = fail

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: dict) -> None:
        if self.fail:
            raise RuntimeError("socket gone")
        self.sent.append(payload)


@pytest.mark.asyncio
async def test_broadcast_tags_envelopes_with_monotonic_id():
    manager = RealtimeManager()
    org = uuid4()
    socket = FakeWebSocket()
    await manager.connect(socket, uuid4(), org_id=org)

    await manager.broadcast({"event": "first", "payload": {}}, org_id=org)
    await manager.broadcast({"event": "second", "payload": {}}, org_id=org)

    assert [event["id"] for event in socket.sent] == [1, 2]
    assert [event["event"] for event in socket.sent] == ["first", "second"]


@pytest.mark.asyncio
async def test_broadcast_is_scoped_to_the_emitting_org():
    """An event for org A must never reach a socket connected under org B."""
    manager = RealtimeManager()
    org_a, org_b = uuid4(), uuid4()
    sock_a = FakeWebSocket()
    sock_b = FakeWebSocket()
    await manager.connect(sock_a, uuid4(), org_id=org_a)
    await manager.connect(sock_b, uuid4(), org_id=org_b)

    await manager.broadcast({"event": "a-only", "payload": {}}, org_id=org_a)

    assert [e["event"] for e in sock_a.sent] == ["a-only"]
    assert sock_b.sent == []


@pytest.mark.asyncio
async def test_broadcast_without_org_context_is_dropped():
    """No org (arg or contextvar) => the event is dropped, never fanned out globally."""
    manager = RealtimeManager()
    socket = FakeWebSocket()
    await manager.connect(socket, uuid4(), org_id=uuid4())

    await manager.broadcast({"event": "orphan", "payload": {}})  # no org_id, no contextvar

    assert socket.sent == []


@pytest.mark.asyncio
async def test_reconnect_replays_missed_events_using_last_event_id():
    manager = RealtimeManager()
    org = uuid4()
    user_id = uuid4()

    # First client connects, receives two events, then disconnects.
    first = FakeWebSocket()
    await manager.connect(first, user_id, org_id=org)
    await manager.broadcast({"event": "a", "payload": {}}, org_id=org)
    await manager.broadcast({"event": "b", "payload": {}}, org_id=org)
    manager.disconnect(first, user_id)

    # Third event arrives while nobody is listening.
    await manager.broadcast({"event": "c", "payload": {}}, org_id=org)

    # Reconnect with last_event_id=2 — should receive only event "c".
    second = FakeWebSocket()
    await manager.connect(second, user_id, org_id=org, last_event_id=2)

    assert [event["event"] for event in second.sent] == ["c"]
    assert second.sent[0]["id"] == 3


@pytest.mark.asyncio
async def test_reconnect_without_last_event_id_skips_replay():
    manager = RealtimeManager()
    org = uuid4()
    user_id = uuid4()

    await manager.broadcast({"event": "a", "payload": {}}, org_id=org)
    await manager.broadcast({"event": "b", "payload": {}}, org_id=org)

    socket = FakeWebSocket()
    await manager.connect(socket, user_id, org_id=org)

    assert socket.sent == []


@pytest.mark.asyncio
async def test_reconnect_only_replays_its_own_orgs_buffer():
    """Replay is per-org: a reconnecting client never sees another org's backlog."""
    manager = RealtimeManager()
    org_a, org_b = uuid4(), uuid4()
    await manager.broadcast({"event": "a1", "payload": {}}, org_id=org_a)
    await manager.broadcast({"event": "b1", "payload": {}}, org_id=org_b)

    sock = FakeWebSocket()
    await manager.connect(sock, uuid4(), org_id=org_b, last_event_id=0)

    assert [e["event"] for e in sock.sent] == ["b1"]


@pytest.mark.asyncio
async def test_broadcast_to_user_does_not_enter_replay_buffer():
    manager = RealtimeManager()
    org = uuid4()
    user_id = uuid4()

    targeted = FakeWebSocket()
    await manager.connect(targeted, user_id, org_id=org)
    await manager.broadcast_to_user(user_id, {"event": "targeted", "payload": {}})

    # A fresh subscriber reconnects asking for everything; targeted events should
    # NOT be replayed because they were never broadcast to the org buffer.
    fresh = FakeWebSocket()
    await manager.connect(fresh, uuid4(), org_id=org, last_event_id=0)

    assert fresh.sent == []


@pytest.mark.asyncio
async def test_stale_socket_is_cleaned_up_on_fan_out_failure():
    manager = RealtimeManager()
    org = uuid4()
    user_id = uuid4()
    failing = FakeWebSocket(fail=True)
    await manager.connect(failing, user_id, org_id=org)

    await manager.broadcast({"event": "x", "payload": {}}, org_id=org)

    assert failing not in manager._org_connections.get(org, set())
    assert user_id not in manager._user_connections
    assert failing not in manager._socket_org


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, None),
        ("", None),
        ("abc", None),
        ("-1", None),
        ("0", 0),
        ("42", 42),
    ],
)
def test_parse_last_event_id(value, expected):
    assert _parse_last_event_id(value) == expected
