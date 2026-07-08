"""Add payment_receipts table (collection ledger).

Each row is one payment transaction (amount, date, mode, reference) posted
against a booking and optionally a specific installment (payment_schedules).

Revision ID: 20260710_t008
Revises: 20260710_t007
Create Date: 2026-07-10 11:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260710_t008"
down_revision: str | None = "20260710_t007"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payment_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("schedule_id", sa.Uuid(), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("paid_on", sa.Date(), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("reference", sa.String(120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["schedule_id"], ["payment_schedules.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payment_receipts_booking", "payment_receipts", ["booking_id"])
    op.create_index("ix_payment_receipts_schedule_id", "payment_receipts", ["schedule_id"])


def downgrade() -> None:
    op.drop_table("payment_receipts")
