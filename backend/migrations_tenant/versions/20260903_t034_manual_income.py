"""Finance vertical Phase 2 — manual_income (non-sale income: interest/rent/misc).

Reuses the public gst_treatment_enum (create_type=False). Chains onto the Phase-1
tenant migration t033.

Revision ID: 20260903_t034
Revises: 20260903_t033
Create Date: 2026-09-03 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260903_t034"
down_revision: str | None = "20260903_t033"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_USERS = "public.users.id"


def upgrade() -> None:
    op.create_table(
        "manual_income",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
        sa.Column("income_number", sa.String(32), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(120), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("income_date", sa.Date(), nullable=False),
        sa.Column("payment_mode", sa.String(32), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        # GST/amount group (mirrors expenses / vendor_bills)
        sa.Column("gst_applicable", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "gst_treatment",
            postgresql.ENUM("intra_state", "inter_state", name="gst_treatment_enum", create_type=False, schema="public"),
            nullable=True,
        ),
        sa.Column("gst_inclusive", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("gst_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("amount_entered", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("taxable_amount", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("cgst_amount", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("sgst_amount", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("igst_amount", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("tds_amount", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("total_amount", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("net_payable", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.CheckConstraint("amount_entered >= 0", name="ck_manual_income_amount_non_negative"),
        sa.ForeignKeyConstraint(["category_id"], ["finance_categories.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], [_USERS], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], [_USERS], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deleted_by_id"], [_USERS], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("income_number", name="uq_manual_income_income_number"),
    )
    op.create_index("ix_manual_income_category", "manual_income", ["category_id"])
    op.create_index("ix_manual_income_date", "manual_income", ["income_date"])
    op.create_index("ix_manual_income_project_id", "manual_income", ["project_id"])


def downgrade() -> None:
    op.drop_table("manual_income")
