"""Add is_active flag to organizations table.

Platform admins can disable (suspend) a client organization without deleting
it. `is_active=false` blocks the org's users from logging in and from making
authenticated requests. Existing orgs default to active.

Revision ID: 20260630_0104
Revises: 20260623_0103
Create Date: 2026-06-30 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260630_0104"
down_revision: str | None = "20260623_0103"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.create_index("ix_organizations_is_active", "organizations", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_organizations_is_active", table_name="organizations")
    op.drop_column("organizations", "is_active")
