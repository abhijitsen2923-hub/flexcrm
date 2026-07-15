"""Add booking_refunds — refund issued when a paid booking is cancelled.

A paid booking cannot simply be cancelled (the cancel guard blocks it); it is
cancelled by recording a refund. `gross_paid` snapshots the collected total,
`deduction_amount` is the forfeiture withheld, `refund_amount` the net returned.

Revision ID: 20260715_t016
Revises: 20260715_t015
Create Date: 2026-07-15 13:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260715_t016"
down_revision: str | None = "20260715_t015"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "booking_refunds",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("gross_paid", sa.Numeric(14, 2), nullable=False),
        sa.Column("deduction_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("refund_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("refunded_on", sa.Date(), nullable=False),
        sa.Column("reference", sa.String(120), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_booking_refunds_booking", "booking_refunds", ["booking_id"])


def downgrade() -> None:
    op.drop_table("booking_refunds")
