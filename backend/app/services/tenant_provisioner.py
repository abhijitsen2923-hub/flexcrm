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
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization


logger = logging.getLogger(__name__)

# Validates schema names before using them in raw SQL.
# Format: starts with lowercase letter, only lowercase alphanumeric + underscore, max 63 chars.
_SAFE_SCHEMA = re.compile(r"^[a-z][a-z0-9_]{0,62}$")

# Path to the tenant Alembic config file, relative to where the app runs from.
_ALEMBIC_TENANT_INI = "alembic_tenant.ini"


async def provision_tenant(org: Organization, session: AsyncSession) -> None:
    """Create the tenant schema for `org` and run all tenant migrations.

    Steps:
    1. Validate schema_name is safe for raw SQL interpolation.
    2. CREATE SCHEMA IF NOT EXISTS (idempotent).
    3. Run tenant Alembic migrations for this schema (idempotent via alembic_version).

    This must be called AFTER org.schema_name is set and AFTER the session has
    been flushed so org.id exists. Call it before committing the org row so
    the transaction can be rolled back if provisioning fails.

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

    # Step 1: Create schema. Double-quoted identifier prevents SQL injection even
    # though the regex above already guarantees the name is safe.
    await session.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
    # Flush so the schema exists in the DB before Alembic tries to write to it.
    await session.flush()

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
