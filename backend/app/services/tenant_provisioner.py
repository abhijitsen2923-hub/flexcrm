"""Tenant provisioning: create a PostgreSQL schema and run tenant migrations.

Called once per org at registration time. Idempotent: CREATE SCHEMA IF NOT
EXISTS and Alembic's up-to-date check both skip work if already done.
"""
import asyncio
import logging
import os
import re

from alembic import command as alembic_cmd
from alembic.config import Config
from sqlalchemy import text

from app.database.session import db_manager
from app.models.organization import Organization


logger = logging.getLogger(__name__)

# Validates schema names before using them in raw SQL.
# Format: starts with lowercase letter, only lowercase alphanumeric + underscore, max 63 chars.
_SAFE_SCHEMA = re.compile(r"^[a-z][a-z0-9_]{0,62}$")

# Path to the tenant Alembic config file, relative to where the app runs from.
_ALEMBIC_TENANT_INI = "alembic_tenant.ini"


async def provision_tenant(org: Organization) -> None:
    """Create the tenant schema for `org` and run all tenant migrations.

    Steps:
    1. Validate schema_name is safe for raw SQL interpolation.
    2. CREATE SCHEMA IF NOT EXISTS — committed immediately in its own transaction.
    3. Run tenant Alembic migrations for this schema (idempotent via alembic_version).

    The schema creation MUST be committed before Alembic migrations run because
    Alembic opens its own separate psycopg2 connection, which only sees committed
    DDL (PostgreSQL default READ COMMITTED isolation). Running CREATE SCHEMA inside
    the caller's open transaction would leave it invisible to Alembic → migrations
    fail with "schema does not exist" on every registration attempt.

    CREATE SCHEMA IF NOT EXISTS is idempotent: an orphaned schema from a failed
    registration is harmless — it stays empty until the next attempt succeeds.

    Raises ValueError for an invalid schema name.
    Raises RuntimeError if migrations fail.
    """
    schema = org.schema_name
    if not _SAFE_SCHEMA.match(schema):
        raise ValueError(
            f"Cannot provision tenant: schema name {schema!r} contains unsafe characters. "
            "Expected lowercase alphanumeric and underscores, starting with a letter, max 63 chars."
        )

    logger.info("provision_tenant: creating schema %r for org %s", schema, org.id)

    # Step 1: Create schema in its own committed transaction so that the Alembic
    # thread's separate connection can see it immediately.
    async with db_manager.engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))

    # Step 2: Run tenant migrations in a thread (Alembic is synchronous).
    try:
        await asyncio.to_thread(_run_tenant_migrations, schema)
    except Exception as exc:
        logger.error("provision_tenant: migration failed for schema %r: %s", schema, exc)
        raise RuntimeError(f"Tenant migration failed for schema {schema!r}: {exc}") from exc

    logger.info("provision_tenant: schema %r is ready", schema)


def _run_tenant_migrations(schema_name: str) -> None:
    """Synchronous helper that runs Alembic inside a thread pool worker."""
    env = os.environ.copy()
    env["TARGET_SCHEMA"] = schema_name

    # Temporarily set TARGET_SCHEMA in the process environment so env.py picks it up.
    old = os.environ.get("TARGET_SCHEMA")
    os.environ["TARGET_SCHEMA"] = schema_name
    try:
        cfg = Config(_ALEMBIC_TENANT_INI)
        alembic_cmd.upgrade(cfg, "head")
    finally:
        if old is None:
            os.environ.pop("TARGET_SCHEMA", None)
        else:
            os.environ["TARGET_SCHEMA"] = old
