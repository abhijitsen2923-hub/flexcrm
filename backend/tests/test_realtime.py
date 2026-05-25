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
    socket = FakeWebSocket()
    await manager.connect(socket, uuid4())

    await manager.broadcast({"event": "first", "payload": {}})
    await manager.broadcast({"event": "second", "payload": {}})

    assert [event["id"] for event in socket.sent] == [1, 2]
    assert [event["event"] for event in socket.sent] == ["first", "second"]


@pytest.mark.asyncio
async def test_reconnect_replays_missed_events_using_last_event_id():
    manager = RealtimeManager()
    user_id = uuid4()

    # First client connects, receives two events, then disconnects.
    first = FakeWebSocket()
    await manager.connect(first, user_id)
    await manager.broadcast({"event": "a", "payload": {}})
    await manager.broadcast({"event": "b", "payload": {}})
    manager.disconnect(first, user_id)

    # Third event arrives while nobody is listening.
    await manager.broadcast({"event": "c", "payload": {}})

    # Reconnect with last_event_id=2 — should receive only event "c".
    second = FakeWebSocket()
    await manager.connect(second, user_id, last_event_id=2)

    assert [event["event"] for event in second.sent] == ["c"]
    assert second.sent[0]["id"] == 3


@pytest.mark.asyncio
async def test_reconnect_without_last_event_id_skips_replay():
    manager = RealtimeManager()
    user_id = uuid4()

    await manager.broadcast({"event": "a", "payload": {}})
    await manager.broadcast({"event": "b", "payload": {}})

    socket = FakeWebSocket()
    await manager.connect(socket, user_id)

    assert socket.sent == []


@pytest.mark.asyncio
async def test_broadcast_to_user_does_not_enter_replay_buffer():
    manager = RealtimeManager()
    user_id = uuid4()

    targeted = FakeWebSocket()
    await manager.connect(targeted, user_id)
    await manager.broadcast_to_user(user_id, {"event": "targeted", "payload": {}})

    # Now a fresh subscriber reconnects asking for everything; targeted events
    # should NOT be replayed because they were never broadcast.
    fresh = FakeWebSocket()
    await manager.connect(fresh, uuid4(), last_event_id=0)

    assert fresh.sent == []


@pytest.mark.asyncio
async def test_stale_socket_is_cleaned_up_on_fan_out_failure():
    manager = RealtimeManager()
    user_id = uuid4()
    failing = FakeWebSocket(fail=True)
    await manager.connect(failing, user_id)

    await manager.broadcast({"event": "x", "payload": {}})

    assert failing not in manager._broadcast_connections
    assert user_id not in manager._connections


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
