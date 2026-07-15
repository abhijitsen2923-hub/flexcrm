"""Add 'receptionist' to user_role_enum (entry-only real-estate front-desk role).

Revision ID: 20260715_0107
Revises: 20260706_0106
Create Date: 2026-07-15 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260715_0107"
down_revision: str | None = "20260706_0106"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # PG12+ allows ADD VALUE inside a transaction as long as the value isn't used
    # in the same transaction (it isn't here). IF NOT EXISTS makes it idempotent.
    op.execute("ALTER TYPE user_role_enum ADD VALUE IF NOT EXISTS 'receptionist'")


def downgrade() -> None:
    # PostgreSQL cannot remove an enum value; no-op.
    pass
