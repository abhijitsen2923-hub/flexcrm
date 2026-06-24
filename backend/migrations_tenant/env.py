"""Alembic env.py for the per-tenant schema track.

Usage
-----
Apply all tenant schemas (batch mode, used during upgrades):
    alembic -c alembic_tenant.ini upgrade head

Apply a single tenant schema (used by provision_tenant()):
    TARGET_SCHEMA=travel_make_my_trip alembic -c alembic_tenant.ini upgrade head

Generate a new tenant migration (auto-generate from TenantBase.metadata):
    alembic -c alembic_tenant.ini revision --autogenerate -m "add_column_x_to_leads"
"""
from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from app.core.config import get_settings
from app.database.base import TenantBase
# Import all models so TenantBase.metadata is fully populated.
import app.models  # noqa: F401
import app.finance.models  # noqa: F401
import app.hr.models  # noqa: F401
import app.real_estate.models  # noqa: F401
import app.customer_portal.models  # noqa: F401
import app.models.custom_role  # noqa: F401


config = context.config
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.sync_database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = TenantBase.metadata


def run_migrations_for_schema(schema_name: str, connection) -> None:
    """Apply (or verify) tenant migrations against schema_name."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table="alembic_version",
        version_table_schema=schema_name,
    )
    with context.begin_transaction():
        # SET LOCAL scopes search_path to this transaction only.
        # MUST be inside begin_transaction() — calling connection.execute()
        # before begin_transaction() triggers SQLAlchemy 2.x autobegin,
        # causing Alembic to use a SAVEPOINT whose outer transaction is then
        # rolled back on connection close → 0 tables in the tenant schema.
        connection.execute(
            text(f'SET LOCAL search_path TO "{schema_name}", public')
        )
        context.run_migrations()
    # SET LOCAL expires on commit; no explicit restore needed.


def run_migrations_offline() -> None:
    """Generate SQL scripts without a live DB connection (review mode)."""
    target_schema = os.environ.get("TARGET_SCHEMA", "example_tenant")
    context.configure(
        url=settings.sync_database_url,
        target_metadata=target_metadata,
        version_table="alembic_version",
        version_table_schema=target_schema,
        include_schemas=True,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = settings.sync_database_url
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        target_schema = os.environ.get("TARGET_SCHEMA")
        if target_schema:
            # Single-schema mode: provision_tenant() sets TARGET_SCHEMA before calling.
            run_migrations_for_schema(target_schema, connection)
        else:
            # Batch mode: migrate all active organizations during upgrade deploys.
            rows = connection.execute(
                text("SELECT schema_name FROM organizations WHERE is_deleted = false")
            ).fetchall()
            for row in rows:
                run_migrations_for_schema(row.schema_name, connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
