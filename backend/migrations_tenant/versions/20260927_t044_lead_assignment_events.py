"""Create lead_assignment_events — owner-assignment history shown in a lead's Stage History.

One row per owner change (from → to, by whom, how). Kept out of stage_transitions on purpose (that
table feeds commission re-attribution and the HR scorecard). Per-tenant schema (search_path); FKs to
public.users are fully qualified. Starts empty: past reassignments were never recorded.

Revision ID: 20260927_t044
Revises: 20260917_t043
Create Date: 2026-09-27 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260927_t044"
down_revision: str | None = "20260917_t043"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lead_assignment_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("from_user_id", sa.Uuid(), nullable=True),
        sa.Column("to_user_id", sa.Uuid(), nullable=True),
        sa.Column("performed_by_id", sa.Uuid(), nullable=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("performed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["from_user_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["to_user_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["performed_by_id"], ["public.users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_lead_assignment_events_lead_performed_at",
        "lead_assignment_events",
        ["lead_id", "performed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_lead_assignment_events_lead_performed_at", table_name="lead_assignment_events")
    op.drop_table("lead_assignment_events")
