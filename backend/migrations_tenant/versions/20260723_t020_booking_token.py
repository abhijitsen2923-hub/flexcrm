"""Add token / booking-amount columns to bookings (Phase C — token = booking).

The token is the initial money that confirms a booking (the "Booked / Token"
stage). Kept first-class on the booking — denormalized from the first receipt —
so the lead is the source of truth for it. All columns nullable + additive.

Revision ID: 20260723_t020
Revises: 20260722_t019
Create Date: 2026-07-23 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260723_t020"
down_revision: str | None = "20260722_t019"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


_COLUMNS = [
    ("token_amount", sa.Numeric(14, 2)),
    ("token_received_on", sa.Date()),
    ("token_mode", sa.String(20)),
    ("token_reference", sa.String(120)),
]


def upgrade() -> None:
    for name, coltype in _COLUMNS:
        op.add_column("bookings", sa.Column(name, coltype, nullable=True))


def downgrade() -> None:
    for name, _ in reversed(_COLUMNS):
        op.drop_column("bookings", name)
