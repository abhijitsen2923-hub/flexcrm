"""Add lead_call_logs — per-(lead, user) call tracking.

"First Call Done" / "Follow-up Call Done" are logged per user, so a reassigned
owner records their own first call independently of the previous owner.

Revision ID: 20260715_t015
Revises: 20260715_t014
Create Date: 2026-07-15 11:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260715_t015"
down_revision: str | None = "20260715_t014"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lead_call_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("call_type", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["public.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lead_call_logs_lead", "lead_call_logs", ["lead_id"])
    op.create_index("ix_lead_call_logs_user_id", "lead_call_logs", ["user_id"])


def downgrade() -> None:
    op.drop_table("lead_call_logs")
