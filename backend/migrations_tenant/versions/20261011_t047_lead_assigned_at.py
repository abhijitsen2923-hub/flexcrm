"""Denormalize leads.assigned_at — when the lead was given to its CURRENT owner.

Lets the leads list and the dashboard show "assigned today / yesterday" without a per-request join over the
owner history. Set on every owner change (create with an owner, reassign, bulk reassign, the Booked / Token
salesperson pick); cleared when the lead is unassigned. Backfilled from each lead's latest owner-history row
when that row handed it to its current owner; leads assigned before the history existed (2026-09-27, t044)
stay NULL — there's no record of when they were assigned. Runs per tenant via the migration search_path.

Revision ID: 20261011_t047
Revises: 20260930_t046
Create Date: 2026-10-11 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20261011_t047"
down_revision: str | None = "20260930_t046"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_leads_assigned_at", "leads", ["assigned_at"])
    op.execute(
        """
        UPDATE leads AS l
        SET assigned_at = latest.performed_at
        FROM (
            SELECT DISTINCT ON (lead_id) lead_id, to_user_id, performed_at
            FROM lead_assignment_events
            ORDER BY lead_id, performed_at DESC, id DESC
        ) AS latest
        WHERE latest.lead_id = l.id
          AND l.assigned_to_id IS NOT NULL
          AND latest.to_user_id = l.assigned_to_id
        """
    )


def downgrade() -> None:
    op.drop_index("ix_leads_assigned_at", table_name="leads")
    op.drop_column("leads", "assigned_at")
