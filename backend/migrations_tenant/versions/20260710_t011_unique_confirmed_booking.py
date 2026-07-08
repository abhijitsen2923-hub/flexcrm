"""Anti-oversell: at most one confirmed booking per unit (partial unique index).

Closes the concurrent double-confirm race the app-level status check can't fully
prevent. Drafts and cancelled bookings are unconstrained; only one *confirmed*,
non-deleted booking may exist per unit.

Revision ID: 20260710_t011
Revises: 20260710_t010
Create Date: 2026-07-10 14:00:00.000000
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260710_t011"
down_revision: str | None = "20260710_t010"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_bookings_unit_confirmed "
        "ON bookings (unit_id) WHERE status = 'confirmed' AND is_deleted = false"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_bookings_unit_confirmed")
