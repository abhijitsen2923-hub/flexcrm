"""Denormalize leads.stage_changed_at from the latest stage transition.

Adds `leads.stage_changed_at` — the timestamp of the lead's LATEST stage change —
so the leads list can filter "stage changed between From and To" without a
per-request join. Unlike last_comment_at (bumped by DNP/call-logs), this is a
pure stage-change stamp, set on every stage move + the initial seed. Backfilled
from each lead's latest transition; any lead with no transition rows (e.g. a
customer-portal referral, which builds the Lead directly) falls back to its
created_at so the column is never NULL. Runs per-tenant via the migration
search_path, so `leads`/`stage_transitions` resolve in-schema.

Revision ID: 20260728_t027
Revises: 20260728_t026
Create Date: 2026-07-28 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260728_t027"
down_revision: str | None = "20260728_t026"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("stage_changed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_leads_stage_changed_at", "leads", ["stage_changed_at"])
    # Backfill from each lead's latest transition (latest by performed_at, id).
    op.execute(
        """
        UPDATE leads AS l
        SET stage_changed_at = latest.performed_at
        FROM (
            SELECT DISTINCT ON (lead_id) lead_id, performed_at
            FROM stage_transitions
            ORDER BY lead_id, performed_at DESC, id DESC
        ) AS latest
        WHERE latest.lead_id = l.id
        """
    )
    # Leads with no transition rows (e.g. customer-portal referrals) fall back to
    # their creation time — their stage was set at creation. Keeps the column
    # non-NULL so the "stage changed between" filter never silently drops a lead.
    op.execute(
        "UPDATE leads SET stage_changed_at = created_at WHERE stage_changed_at IS NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_leads_stage_changed_at", table_name="leads")
    op.drop_column("leads", "stage_changed_at")
