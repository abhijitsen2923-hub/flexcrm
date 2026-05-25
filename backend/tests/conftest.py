import os
from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def app(tmp_path, monkeypatch) -> AsyncIterator:
    db_file = tmp_path / "crm_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_file.as_posix()}")
    monkeypatch.setenv("SYNC_DATABASE_URL", f"sqlite:///{db_file.as_posix()}")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-access-secret-key-1234")
    monkeypatch.setenv("JWT_REFRESH_SECRET_KEY", "test-refresh-secret-key-1234")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6399/0")
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "1000")
    monkeypatch.setenv("DOCS_ENABLED", "false")

    from app.core.config import get_settings

    get_settings.cache_clear()

    from app.database.base import Base
    from app.database.pipeline_seed import as_dicts
    from app.database.session import db_manager
    from app.main import create_app
    from app.models.pipeline_stage import PipelineStage
    # Register Finance + HR ORM models with Base.metadata so create_all sees
    # their tables. These packages live outside app/models/ so they don't
    # auto-load via the standard model imports above.
    from app.finance import models as _finance_models  # noqa: F401
    from app.hr import models as _hr_models  # noqa: F401

    db_manager.configure(os.environ["DATABASE_URL"])
    application = create_app()

    async with db_manager.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        # Seed the 30 pipeline_stages rows so the leads endpoint can resolve
        # (industry, stage_code) → stage during tests. Migration does the same
        # in Postgres; this is the in-memory SQLite equivalent.
        await connection.execute(PipelineStage.__table__.insert(), as_dicts())

    try:
        yield application
    finally:
        async with db_manager.engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await db_manager.dispose()
        get_settings.cache_clear()


@pytest_asyncio.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    """First registration creates Organization A; this user is its owner.

    Phase 8 made every first-user-of-an-org `owner` regardless of the request's
    `role` field — the value below is accepted but ignored.
    """
    register_response = await client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Admin",
            "last_name": "User",
            "email": "admin@example.com",
            "password": "StrongPass123",
            "phone": "+1555000001",
            "role": "owner",
            "business_type": "education",
            "organization_name": "Test Org A",
        },
    )
    assert register_response.status_code == 201, register_response.text
    access_token = register_response.json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


@pytest_asyncio.fixture
async def sales_headers(client: AsyncClient, auth_headers: dict[str, str]) -> dict[str, str]:
    """A `counselor` user inside the SAME (Education) org as auth_headers.

    Pre-Phase 8 this was a `sales` user; post-Phase 8 the corresponding
    Education-vertical role is `counselor`. The fixture name is unchanged to
    minimise test churn — call sites care that this is a non-owner sales-flavoured
    role, not that it's literally `sales`.

    `organization_id` is auto-stamped by the tenancy `before_flush` listener
    from the admin's session scope.
    """
    create = await client.post(
        "/api/v1/users",
        headers=auth_headers,
        json={
            "first_name": "Sammy",
            "last_name": "Sales",
            "email": "sales@example.com",
            "password": "StrongPass123",
            "phone": "+1555000002",
            "role": "counselor",
            "status": "active",
        },
    )
    assert create.status_code == 201, create.text

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "sales@example.com", "password": "StrongPass123"},
    )
    assert login.status_code == 200, login.text
    payload = login.json()
    assert payload["user"]["role"] == "counselor"
    return {"Authorization": f"Bearer {payload['access_token']}"}
