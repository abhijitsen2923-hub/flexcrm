"""Create campaigns + campaign_aliases — each tenant's own lead-campaign list and merged/renamed spellings.

DDL only: the list is seeded lazily from the tenant's own leads (services/campaigns.py), so no tenant data
is written here. Per-tenant schema (search_path); FKs to public.users are fully qualified.

Revision ID: 20260928_t045
Revises: 20260927_t044
Create Date: 2026-09-28 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260928_t045"
down_revision: str | None = "20260927_t044"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("name_key", sa.String(240), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("needs_review", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name_key", name="uq_campaigns_name_key"),
        sa.ForeignKeyConstraint(["created_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["public.users.id"], ondelete="SET NULL"),
    )
    op.create_table(
        "campaign_aliases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("alias", sa.String(120), nullable=False),
        sa.Column("alias_key", sa.String(240), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("alias_key", name="uq_campaign_aliases_alias_key"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["public.users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_campaign_aliases_campaign_id", "campaign_aliases", ["campaign_id"])


def downgrade() -> None:
    op.drop_index("ix_campaign_aliases_campaign_id", table_name="campaign_aliases")
    op.drop_table("campaign_aliases")
    op.drop_table("campaigns")
