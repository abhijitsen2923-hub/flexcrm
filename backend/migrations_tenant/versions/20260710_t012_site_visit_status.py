"""Add site_visits.status (scheduled / completed / cancelled).

Revision ID: 20260710_t012
Revises: 20260710_t011
Create Date: 2026-07-10 15:00:00.000000
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260710_t012"
down_revision: str | None = "20260710_t011"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE site_visits ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'scheduled'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE site_visits DROP COLUMN IF EXISTS status")
