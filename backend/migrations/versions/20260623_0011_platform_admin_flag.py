"""Add is_platform_admin flag to users table.

Platform admins (FlexCRM operators) can manage all organizations and toggle
per-org module access. The flag is false for all existing users and must be
set directly in the DB for the first platform admin.

Revision ID: 20260623_0011
Revises: 20260522_0010
Create Date: 2026-06-23 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260623_0011"
down_revision: str | None = "20260522_0010"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_platform_admin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "is_platform_admin")
