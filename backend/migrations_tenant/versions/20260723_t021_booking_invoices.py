"""Add booking_invoices — per-installment demand invoices (Phase C — invoices).

An invoice is a DEMAND raised before collection (distinct from the post-payment
PaymentReceipt). Numbered with a per-tenant sequential series (finance._next_sequence,
prefix INV-RE). Mirrors the finance `invoices` table (same mixins + status enum),
reusing the shared public `invoice_status_enum` PG type (create_type=False).

Revision ID: 20260723_t021
Revises: 20260723_t020
Create Date: 2026-07-23 11:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260723_t021"
down_revision: str | None = "20260723_t020"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "booking_invoices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
        sa.Column("invoice_number", sa.String(32), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("schedule_id", sa.Uuid(), nullable=True),
        sa.Column("installment_name", sa.String(120), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "draft", "issued", "paid", "refunded", "void",
                name="invoice_status_enum", create_type=False, schema="public",
            ),
            nullable=False,
        ),
        sa.CheckConstraint("amount >= 0", name="ck_booking_invoices_amount_non_negative"),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["schedule_id"], ["payment_schedules.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deleted_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invoice_number", name="uq_booking_invoices_invoice_number"),
    )
    op.create_index("ix_booking_invoices_booking_id", "booking_invoices", ["booking_id"])
    op.create_index("ix_booking_invoices_schedule_id", "booking_invoices", ["schedule_id"])


def downgrade() -> None:
    op.drop_index("ix_booking_invoices_schedule_id", table_name="booking_invoices")
    op.drop_index("ix_booking_invoices_booking_id", table_name="booking_invoices")
    op.drop_table("booking_invoices")
