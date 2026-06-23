"""Add `custom` sentinel value to user_role_enum (public schema).

Revision ID: 20260623_0103
Revises: 20260623_0102
Create Date: 2026-06-23 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260623_0103"
down_revision: str | None = "20260623_0102"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            sa.text("ALTER TYPE user_role_enum ADD VALUE IF NOT EXISTS 'custom';")
        )


def downgrade() -> None:
    # Postgres cannot remove enum values; no-op.
    pass
