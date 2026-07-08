"""Add bookings.cancellation_reason (optional note on cancel).

Revision ID: 20260710_t010
Revises: 20260710_t009
Create Date: 2026-07-10 13:00:00.000000
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260710_t010"
down_revision: str | None = "20260710_t009"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS cancellation_reason TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE bookings DROP COLUMN IF EXISTS cancellation_reason")
