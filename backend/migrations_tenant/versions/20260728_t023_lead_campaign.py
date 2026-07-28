"""Add leads.campaign — marketing-campaign attribution (leads-page enhancements).

A secondary attribution dimension alongside `source` (which campaign a lead came
from). Free string, controlled list app-side. Nullable + additive.

Revision ID: 20260728_t023
Revises: 20260724_t022
Create Date: 2026-07-28 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260728_t023"
down_revision: str | None = "20260724_t022"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("campaign", sa.String(120), nullable=True))
    op.create_index("ix_leads_campaign", "leads", ["campaign"])


def downgrade() -> None:
    op.drop_index("ix_leads_campaign", table_name="leads")
    op.drop_column("leads", "campaign")
