"""Add soft-delete columns to projects / towers / units (archive support).

Enables archiving inventory (hide, keep history) instead of hard-deleting rows
that bookings may reference. deleted_by_id mirrors the model's audit ref; the
physical cross-schema FK is intentionally omitted (matches other additive tenant
migrations — the column is audit-only, never joined).

Revision ID: 20260710_t009
Revises: 20260710_t008
Create Date: 2026-07-10 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260710_t009"
down_revision: str | None = "20260710_t008"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_TABLES = ("projects", "towers", "units")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()))
        op.add_column(table, sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
        op.add_column(table, sa.Column("deleted_by_id", sa.Uuid(), nullable=True))
        op.create_index(f"ix_{table}_is_deleted", table, ["is_deleted"])


def downgrade() -> None:
    for table in _TABLES:
        op.drop_index(f"ix_{table}_is_deleted", table_name=table)
        op.drop_column(table, "deleted_by_id")
        op.drop_column(table, "deleted_at")
        op.drop_column(table, "is_deleted")
