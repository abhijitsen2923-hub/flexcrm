"""Denormalize leads.next_action_date from the latest stage transition.

Adds `leads.next_action_date` (mirrors last_comment_at) so the leads list can
filter "calls/follow-ups due on a day" and sort by upcoming action without a
per-request join. Backfilled from each lead's latest transition. Runs per-tenant
via the migration search_path, so `leads`/`stage_transitions` resolve in-schema.

Revision ID: 20260728_t024
Revises: 20260728_t023
Create Date: 2026-07-28 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260728_t024"
down_revision: str | None = "20260728_t023"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("next_action_date", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_leads_next_action_date", "leads", ["next_action_date"])
    # Backfill from each lead's latest transition (latest by performed_at, id).
    op.execute(
        """
        UPDATE leads AS l
        SET next_action_date = latest.next_action_date
        FROM (
            SELECT DISTINCT ON (lead_id) lead_id, next_action_date
            FROM stage_transitions
            ORDER BY lead_id, performed_at DESC, id DESC
        ) AS latest
        WHERE latest.lead_id = l.id
          AND latest.next_action_date IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_leads_next_action_date", table_name="leads")
    op.drop_column("leads", "next_action_date")
