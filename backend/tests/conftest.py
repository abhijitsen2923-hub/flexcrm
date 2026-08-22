"""Shared pytest fixtures.

⚠️  SCHEMA COLLAPSE — read this before adding a test.

Production is PostgreSQL with schema-per-tenant: every per-tenant model declares
``{"schema": "tenant"}`` and :func:`app.core.tenancy.set_tenant_schema` rewrites
that literal to the org's real schema through SQLAlchemy's
``schema_translate_map``.

SQLite cannot model that. It has no ``CREATE SCHEMA``, and cross-*database*
foreign keys are unsupported — while every tenant table carries FKs to
``public.users`` / ``public.pipeline_stages`` (see ``app/database/base.py``).
So ``ATTACH DATABASE`` per tenant is not an option either.

This harness therefore **collapses every schema into one**: the engine carries a
default ``schema_translate_map`` of ``{"tenant": None, "public": None}``, tenant
provisioning is stubbed out, and ``set_tenant_schema`` is neutered.

**Consequence:** these tests exercise BUSINESS LOGIC, not tenant isolation. A
test here can never prove org A's rows are invisible to org B — in this harness
they share a table. Genuine isolation coverage needs a real Postgres; treat any
"cross-org" test below as covering the *application-level* check (an explicit
``organization_id`` predicate, a 404 branch), never the schema boundary.
"""

import os
import re
import sys
from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event


# Both keys must collapse: tenant models resolve through "tenant", and the FK
# stub tables in TenantBase.metadata are declared with schema="public".
COLLAPSED_SCHEMA_MAP: dict[str, None] = {"tenant": None, "public": None}


def _regexp_replace(value, pattern, replacement, flags=""):
    """SQLite shim for PostgreSQL's ``regexp_replace(source, pattern, repl, flags)``.

    ``LeadRepository.duplicate_contact_keys`` and ``find_duplicates``
    (app/repositories/leads.py) normalise phone numbers to digits with this
    Postgres builtin, and it runs on *every* ``GET /leads``. SQLite has no such
    function, so without this shim the primary list endpoint — and therefore most
    of the suite — cannot be exercised at all.

    Postgres semantics: replace only the first match unless the ``g`` flag is
    given; ``i`` means case-insensitive.
    """
    if value is None:
        return None
    flags = flags or ""
    return re.sub(
        pattern,
        replacement,
        value,
        count=0 if "g" in flags else 1,
        flags=re.IGNORECASE if "i" in flags else 0,
    )


def apply_collapsed_schema_patches(monkeypatch) -> None:
    """Make the app runnable against a single-schema SQLite database.

    Call this BEFORE ``db_manager.configure()`` — it wraps ``create_async_engine``
    so every engine carries the collapsing map as a default execution option.
    (A per-connection map would not survive the connection churn that ``commit()``
    causes, and the tenancy listeners that normally re-apply it are disabled here.)

    Imports ``app.main`` first so that every module which did
    ``from ... import set_tenant_schema`` already exists and can be rebound.
    """
    import app.core.tenancy as tenancy_module
    import app.database.session as session_module
    import app.main  # noqa: F401 — populates the module graph before _rebind walks it
    import app.services.tenant_provisioner as provisioner_module

    real_create_async_engine = session_module.create_async_engine

    def _collapsing_engine(url, **kwargs):
        options = dict(kwargs.pop("execution_options", {}) or {})
        options["schema_translate_map"] = COLLAPSED_SCHEMA_MAP
        return real_create_async_engine(url, execution_options=options, **kwargs)

    monkeypatch.setattr(session_module, "create_async_engine", _collapsing_engine)

    async def _collapsed_set_tenant_schema(session, schema_name):
        # Routing is the engine-level map here. Setting session.info["schema_name"]
        # would re-arm the do_orm_execute / after_begin listeners and point every
        # tenant query at a schema SQLite does not have.
        return None

    async def _skip_provision_tenant(org):
        # Real provisioning issues to_regclass / CREATE SCHEMA — Postgres-only DDL.
        return None

    async def _skip_upgrade_all_tenant_schemas():
        return []

    _rebind(
        monkeypatch,
        "set_tenant_schema",
        tenancy_module.set_tenant_schema,
        _collapsed_set_tenant_schema,
    )
    _rebind(
        monkeypatch,
        "provision_tenant",
        provisioner_module.provision_tenant,
        _skip_provision_tenant,
    )
    _rebind(
        monkeypatch,
        "upgrade_all_tenant_schemas",
        provisioner_module.upgrade_all_tenant_schemas,
        _skip_upgrade_all_tenant_schemas,
    )


def _install_sqlite_shims(engine) -> None:
    """Register Postgres-only SQL functions on every new SQLite connection.

    The pool hands out fresh connections, and a UDF is per-connection, so this
    has to run from the ``connect`` event rather than once up front.
    ``aiosqlite.Connection.create_function`` is a coroutine and unusable from
    this sync hook, so reach the underlying ``sqlite3.Connection`` instead.
    """

    @event.listens_for(engine.sync_engine, "connect")
    def _register(dbapi_connection, _record):  # noqa: ANN001
        driver = getattr(dbapi_connection, "driver_connection", None)
        raw = getattr(driver, "_conn", None)
        if raw is not None:
            raw.create_function("regexp_replace", 4, _regexp_replace)


def _rebind(monkeypatch, name: str, original, replacement) -> None:
    """Rebind ``name`` to ``replacement`` in every module that imported it.

    Call sites use ``from app.core.tenancy import set_tenant_schema``, which
    copies the function object into the importing module's namespace — patching
    only the defining module would miss all of them. Test modules import parts
    of ``app`` at collection time, so those bindings already exist by the time a
    fixture runs; walking ``sys.modules`` is what makes the patch reach them.
    """
    for module in list(sys.modules.values()):
        if module is None:
            continue
        try:
            if getattr(module, name, None) is original:
                monkeypatch.setattr(module, name, replacement, raising=False)
        except Exception:  # noqa: BLE001 — lazy/proxy modules can raise on getattr
            continue


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

    apply_collapsed_schema_patches(monkeypatch)

    # `app.main` (imported by the call above) pulls in every model package —
    # app.models, finance, hr, real_estate, customer_portal, custom_role — so
    # BOTH Base.metadata and TenantBase.metadata are fully populated by now.
    from app.database.base import Base, TenantBase
    from app.database.pipeline_seed import as_dicts
    from app.database.session import db_manager
    from app.main import create_app
    from app.models.pipeline_stage import PipelineStage

    db_manager.configure(os.environ["DATABASE_URL"])
    _install_sqlite_shims(db_manager.engine)
    application = create_app()

    async with db_manager.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        # TenantBase second, so its public.* FK stubs collapse onto the real
        # users / pipeline_stages tables created above — create_all's checkfirst
        # then skips them instead of emitting a duplicate CREATE.
        await connection.run_sync(TenantBase.metadata.create_all)
        # Seed the pipeline_stages rows so the leads endpoints can resolve
        # (industry, stage_code) → stage during tests. The migration does the
        # same in Postgres; this is the SQLite equivalent.
        await connection.execute(PipelineStage.__table__.insert(), as_dicts())

    try:
        yield application
    finally:
        async with db_manager.engine.begin() as connection:
            await connection.run_sync(TenantBase.metadata.drop_all)
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
