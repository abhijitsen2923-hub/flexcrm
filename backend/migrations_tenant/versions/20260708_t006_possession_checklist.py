"""Add bookings.possession_checklist (JSON) for the Possession Tracker.

Revision ID: 20260708_t006
Revises: 20260706_t005
Create Date: 2026-07-08 10:00:00.000000
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260708_t006"
down_revision: str | None = "20260706_t005"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS possession_checklist JSON")


def downgrade() -> None:
    op.execute("ALTER TABLE bookings DROP COLUMN IF EXISTS possession_checklist")
