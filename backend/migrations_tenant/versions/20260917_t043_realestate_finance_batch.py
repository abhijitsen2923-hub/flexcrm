"""Real-estate/finance batch: projects.demand_schedule + vendors POC.

`projects.demand_schedule` (JSON) holds the builder's demand plan — a list of
{label, percent, due_date} milestones a booking inherits (percent of the unit price on
fixed dates). `vendors.poc_name`/`poc_phone` add an explicit point-of-contact beside the
existing contact_name/phone. Per-tenant schema.

Revision ID: 20260917_t043
Revises: 20260915_t042
Create Date: 2026-09-17 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260917_t043"
down_revision: str | None = "20260915_t042"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("demand_schedule", sa.JSON(), nullable=True))
    op.add_column("vendors", sa.Column("poc_name", sa.String(255), nullable=True))
    op.add_column("vendors", sa.Column("poc_phone", sa.String(40), nullable=True))


def downgrade() -> None:
    op.drop_column("vendors", "poc_phone")
    op.drop_column("vendors", "poc_name")
    op.drop_column("projects", "demand_schedule")
