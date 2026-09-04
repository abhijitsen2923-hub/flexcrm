"""Finance Phase 3a — per-customer demand ledger: contracts, demands, receipts.

A customer_contract holds a total (e.g. ₹50L); ad-hoc customer_demands (any
amount, any number) are raised against it; demand_receipts reduce the demand's
outstanding and the contract balance. Statuses are plain strings — no PG enum.

Revision ID: 20260904_t035
Revises: 20260903_t034
Create Date: 2026-09-04 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260904_t035"
down_revision: str | None = "20260903_t034"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_USERS = "public.users.id"


def _mixins() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
    ]


def _audit_fks() -> list[sa.ForeignKeyConstraint]:
    return [
        sa.ForeignKeyConstraint(["created_by_id"], [_USERS], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], [_USERS], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deleted_by_id"], [_USERS], ondelete="SET NULL"),
    ]


def upgrade() -> None:
    op.create_table(
        "customer_contracts",
        sa.Column("id", sa.Uuid(), nullable=False),
        *_mixins(),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("contract_value", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("currency", sa.String(3), server_default="INR", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), server_default="active", nullable=False),
        sa.CheckConstraint("contract_value >= 0", name="ck_customer_contracts_value_non_negative"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="RESTRICT"),
        *_audit_fks(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_customer_contracts_customer", "customer_contracts", ["customer_id"])

    op.create_table(
        "customer_demands",
        sa.Column("id", sa.Uuid(), nullable=False),
        *_mixins(),
        sa.Column("demand_number", sa.String(32), nullable=False),
        sa.Column("contract_id", sa.Uuid(), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(16), server_default="open", nullable=False),
        sa.Column("amount_received", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.CheckConstraint("amount >= 0", name="ck_customer_demands_amount_non_negative"),
        sa.ForeignKeyConstraint(["contract_id"], ["customer_contracts.id"], ondelete="RESTRICT"),
        *_audit_fks(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("demand_number", name="uq_customer_demands_demand_number"),
    )
    op.create_index("ix_customer_demands_contract", "customer_demands", ["contract_id"])
    op.create_index("ix_customer_demands_status", "customer_demands", ["status"])

    op.create_table(
        "demand_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("receipt_number", sa.String(32), nullable=False),
        sa.Column("demand_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("received_on", sa.Date(), nullable=False),
        sa.Column("method", sa.String(64), nullable=True),
        sa.Column("txn_ref", sa.String(120), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("recorded_by_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("amount > 0", name="ck_demand_receipts_amount_positive"),
        sa.ForeignKeyConstraint(["demand_id"], ["customer_demands.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recorded_by_id"], [_USERS], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("receipt_number", name="uq_demand_receipts_receipt_number"),
    )
    op.create_index("ix_demand_receipts_demand", "demand_receipts", ["demand_id"])


def downgrade() -> None:
    op.drop_table("demand_receipts")
    op.drop_table("customer_demands")
    op.drop_table("customer_contracts")
