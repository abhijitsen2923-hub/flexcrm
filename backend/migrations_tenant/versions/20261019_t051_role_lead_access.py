"""Custom roles can limit which leads their users see: chosen campaigns, chosen sources, and/or only the leads
assigned to them.

custom_roles.lead_campaign_ids — JSON list of campaigns.id (ids, not names: a campaign rename keeps its id; a merge
repoints them, see CampaignService.merge). NULL = every campaign.
custom_roles.lead_sources — JSON list of source labels (matched ignoring case and surrounding spaces). NULL = every
source.
custom_roles.lead_own_only — only leads assigned to the user.

Additive and nullable (or NOT NULL with a default), so code from before this revision keeps working against it.
Runs per tenant via the migration search_path.

Revision ID: 20261019_t051
Revises: 20261013_t050
Create Date: 2026-10-19 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20261019_t051"
down_revision: str | None = "20261013_t050"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("custom_roles", sa.Column("lead_campaign_ids", sa.JSON(), nullable=True))
    op.add_column("custom_roles", sa.Column("lead_sources", sa.JSON(), nullable=True))
    op.add_column(
        "custom_roles", sa.Column("lead_own_only", sa.Boolean(), nullable=False, server_default=sa.false())
    )


def downgrade() -> None:
    op.drop_column("custom_roles", "lead_own_only")
    op.drop_column("custom_roles", "lead_sources")
    op.drop_column("custom_roles", "lead_campaign_ids")
