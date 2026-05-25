"""Integration tests for the WebSocket auth handshake.

These tests use starlette's sync `TestClient` (the only way to exercise the
WebSocket upgrade against an in-process app), so they are NOT async fixtures
and do not share the `client` / `auth_headers` fixtures from conftest.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from starlette.websockets import WebSocketDisconnect


@pytest.fixture
def ws_client(tmp_path, monkeypatch):
    db_file = tmp_path / "ws_test.db"
    sync_url = f"sqlite:///{db_file.as_posix()}"
    async_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"

    monkeypatch.setenv("DATABASE_URL", async_url)
    monkeypatch.setenv("SYNC_DATABASE_URL", sync_url)
    monkeypatch.setenv("JWT_SECRET_KEY", "test-access-secret-key-1234")
    monkeypatch.setenv("JWT_REFRESH_SECRET_KEY", "test-refresh-secret-key-1234")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6399/0")
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "1000")
    monkeypatch.setenv("DOCS_ENABLED", "false")

    from app.core.config import get_settings

    get_settings.cache_clear()

    # Materialize the schema synchronously so the async app shares the same db file.
    from app import models  # noqa: F401  registers ORM models against the metadata
    from app.database.base import Base

    sync_engine = create_engine(sync_url)
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()

    from app.database.session import db_manager
    from app.main import create_app

    db_manager.configure(async_url)
    application = create_app()

    with TestClient(application) as client:
        yield client

    teardown_engine = create_engine(sync_url)
    Base.metadata.drop_all(teardown_engine)
    teardown_engine.dispose()
    get_settings.cache_clear()


def _register_and_get_token(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "WS",
            "last_name": "Tester",
            "email": "ws.tester@example.com",
            "password": "StrongPass123",
            "role": "admin",
            "business_type": "education",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def test_websocket_rejects_missing_token(ws_client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect):
        with ws_client.websocket_connect("/api/v1/ws/updates"):
            pass


def test_websocket_rejects_invalid_token(ws_client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect):
        with ws_client.websocket_connect("/api/v1/ws/updates?token=not-a-real-jwt"):
            pass


def test_websocket_rejects_refresh_token(ws_client: TestClient) -> None:
    response = ws_client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "WS",
            "last_name": "Refresh",
            "email": "ws.refresh@example.com",
            "password": "StrongPass123",
            "role": "admin",
            "business_type": "education",
        },
    )
    assert response.status_code == 201
    refresh_token = response.json()["refresh_token"]

    with pytest.raises(WebSocketDisconnect):
        with ws_client.websocket_connect(f"/api/v1/ws/updates?token={refresh_token}"):
            pass


def test_websocket_accepts_valid_access_token(ws_client: TestClient) -> None:
    token = _register_and_get_token(ws_client)
    with ws_client.websocket_connect(f"/api/v1/ws/updates?token={token}") as websocket:
        # Connection accepted — close cleanly. If auth had failed, the context
        # manager entry would have raised WebSocketDisconnect.
        websocket.close()
