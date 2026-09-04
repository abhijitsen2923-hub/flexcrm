"""Finance Phase 3 — bank & cash accounts + transactions (reconciliation).

Adds `finance_accounts` (bank/cash, opening balance) and `bank_transactions`
(in/out movements with an is_reconciled flag). Types are plain strings guarded by
CHECK constraints — no PG enum, so this is a pure per-tenant migration.

Revision ID: 20260904_t038
Revises: 20260904_t037
Create Date: 2026-09-04 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260904_t038"
down_revision: str | None = "20260904_t037"
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
        "finance_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        *_mixins(),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("account_type", sa.String(8), server_default="bank", nullable=False),
        sa.Column("opening_balance", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("currency", sa.String(3), server_default="INR", nullable=False),
        sa.Column("account_number", sa.String(40), nullable=True),
        sa.Column("ifsc", sa.String(15), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.CheckConstraint("account_type in ('bank','cash')", name="ck_finance_accounts_type"),
        *_audit_fks(),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "bank_transactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        *_mixins(),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("txn_date", sa.Date(), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("direction", sa.String(3), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("reference", sa.String(120), nullable=True),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("is_reconciled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("reconciled_on", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint("amount > 0", name="ck_bank_transactions_amount_positive"),
        sa.CheckConstraint("direction in ('in','out')", name="ck_bank_transactions_direction"),
        sa.ForeignKeyConstraint(["account_id"], ["finance_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["finance_categories.id"], ondelete="SET NULL"),
        *_audit_fks(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bank_transactions_account", "bank_transactions", ["account_id"])


def downgrade() -> None:
    op.drop_table("bank_transactions")
    op.drop_table("finance_accounts")
