"""Lead intent (High / Medium / Low): leads.intent, stage_transitions.intent, lead_intent_changes.

`leads.intent` is the lead's current intent (NULL = not rated), indexed for the leads-list filter and checked
to the three values. `stage_transitions.intent` records the intent chosen with each stage change.
`lead_intent_changes` keeps every change incl. those made without a stage change. All nullable / new —
existing rows are untouched (every lead starts "not rated"). Per-tenant schema (search_path); FKs to
public.users are fully qualified.

Revision ID: 20260930_t046
Revises: 20260928_t045
Create Date: 2026-09-30 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260930_t046"
down_revision: str | None = "20260928_t045"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("intent", sa.String(8), nullable=True))
    op.create_check_constraint("ck_leads_intent", "leads", "intent IN ('high', 'medium', 'low')")
    op.create_index("ix_leads_intent", "leads", ["intent"])
    op.add_column("stage_transitions", sa.Column("intent", sa.String(8), nullable=True))
    op.create_table(
        "lead_intent_changes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("from_intent", sa.String(8), nullable=True),
        sa.Column("to_intent", sa.String(8), nullable=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("performed_by_id", sa.Uuid(), nullable=True),
        sa.Column("performed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["performed_by_id"], ["public.users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_lead_intent_changes_lead_performed_at", "lead_intent_changes", ["lead_id", "performed_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_lead_intent_changes_lead_performed_at", table_name="lead_intent_changes")
    op.drop_table("lead_intent_changes")
    op.drop_column("stage_transitions", "intent")
    op.drop_index("ix_leads_intent", table_name="leads")
    op.drop_constraint("ck_leads_intent", "leads", type_="check")
    op.drop_column("leads", "intent")
