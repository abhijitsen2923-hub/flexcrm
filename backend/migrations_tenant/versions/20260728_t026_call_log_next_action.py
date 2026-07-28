"""Add lead_call_logs.next_action_date (schedule a callback from a call/DNP).

A DNP (did-not-pick) — and any call — can now schedule the next call. The value
is denormalized onto leads.next_action_date by the service so it feeds the leads
date-filter + follow-up reminders. Nullable + additive.

Revision ID: 20260728_t026
Revises: 20260728_t025
Create Date: 2026-07-28 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260728_t026"
down_revision: str | None = "20260728_t025"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("lead_call_logs", sa.Column("next_action_date", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("lead_call_logs", "next_action_date")
