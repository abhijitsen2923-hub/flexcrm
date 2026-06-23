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
        # Each schema tracks its own migration version independently.
        version_table_schema=schema_name,
        include_schemas=True,
        compare_type=True,
        compare_server_default=True,
        # Alembic needs a search_path context to resolve unqualified names in
        # migration scripts. We set public last so cross-schema FK names like
        # "public.users" still resolve without the prefix being mandatory.
        render_as_batch=False,
    )
    # Point search_path at the target schema so DDL lands in the right place.
    connection.execute(text(f'SET search_path TO "{schema_name}", public'))
    with context.begin_transaction():
        context.run_migrations()
    # Restore default search_path after migrations.
    connection.execute(text("SET search_path TO public"))


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
