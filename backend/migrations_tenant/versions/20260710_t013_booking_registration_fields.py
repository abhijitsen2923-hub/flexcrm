"""Add bookings.registration_number + sub_registrar_office (registration record).

Revision ID: 20260710_t013
Revises: 20260710_t012
Create Date: 2026-07-10 15:30:00.000000
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260710_t013"
down_revision: str | None = "20260710_t012"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS registration_number VARCHAR(120)")
    op.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS sub_registrar_office VARCHAR(255)")


def downgrade() -> None:
    op.execute("ALTER TABLE bookings DROP COLUMN IF EXISTS sub_registrar_office")
    op.execute("ALTER TABLE bookings DROP COLUMN IF EXISTS registration_number")
