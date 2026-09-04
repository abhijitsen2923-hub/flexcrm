"""Finance Phase 3 — budgets + expense approval threshold.

Adds a monthly `budgets` table (optional category/department scope; actual spend
computed at read time from expenses) and an `expense_approval_threshold` column on
`finance_settings` (expenses at/above it, when > 0, require a higher approver).

Revision ID: 20260904_t037
Revises: 20260904_t036
Create Date: 2026-09-04 11:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260904_t037"
down_revision: str | None = "20260904_t036"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_USERS = "public.users.id"


def _audit_fks() -> list[sa.ForeignKeyConstraint]:
    return [
        sa.ForeignKeyConstraint(["created_by_id"], [_USERS], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], [_USERS], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deleted_by_id"], [_USERS], ondelete="SET NULL"),
    ]


def upgrade() -> None:
    op.add_column(
        "finance_settings",
        sa.Column("expense_approval_threshold", sa.Numeric(14, 2), server_default="0", nullable=False),
    )

    op.create_table(
        "budgets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("period_key", sa.String(7), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("department", sa.String(80), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint("amount >= 0", name="ck_budgets_amount_non_negative"),
        sa.ForeignKeyConstraint(["category_id"], ["finance_categories.id"], ondelete="SET NULL"),
        *_audit_fks(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_budgets_period", "budgets", ["period_key"])


def downgrade() -> None:
    op.drop_table("budgets")
    op.drop_column("finance_settings", "expense_approval_threshold")
