"""Add users.is_system — flag for non-human service accounts.

The Meta-integration ingest owns leads under a per-org "integration" service user
(so externally-ingested leads have a valid, non-human creator). This flag marks
such accounts so they're excluded from user listings / assignee pickers. Public
schema (users is a shared table). Defaults false for all existing rows.

Revision ID: 20260805_0109
Revises: 20260722_0108
Create Date: 2026-08-05 09:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260805_0109"
down_revision: str | None = "20260722_0108"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("users", "is_system")
