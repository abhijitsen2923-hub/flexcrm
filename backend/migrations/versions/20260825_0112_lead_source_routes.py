"""Create lead_source_routes — public token→tenant router for inbound portal webhooks.

Generalised sibling of meta_page_routes for push portals (99acres, later MagicBricks/Housing).
Maps the SHA-256 hash of a URL path token → its owning org + schema so an unauthenticated
webhook resolves the tenant before touching a tenant schema. Holds NO plaintext secret and no
PII. UNIQUE token_hash; UNIQUE(provider, external_account_id) → one portal account ↔ one tenant.
Public schema (shared).

Revision ID: 20260825_0112
Revises: 20260817_0111
Create Date: 2026-08-25 09:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260825_0112"
down_revision: str | None = "20260817_0111"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lead_source_routes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("external_account_id", sa.String(64), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("schema_name", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("provider", "external_account_id", name="uq_lead_source_routes_provider_account"),
    )
    op.create_index("ix_lead_source_routes_provider", "lead_source_routes", ["provider"])
    op.create_index("ix_lead_source_routes_token_hash", "lead_source_routes", ["token_hash"], unique=True)
    op.create_index("ix_lead_source_routes_external_account_id", "lead_source_routes", ["external_account_id"])
    op.create_index("ix_lead_source_routes_organization_id", "lead_source_routes", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_lead_source_routes_organization_id", table_name="lead_source_routes")
    op.drop_index("ix_lead_source_routes_external_account_id", table_name="lead_source_routes")
    op.drop_index("ix_lead_source_routes_token_hash", table_name="lead_source_routes")
    op.drop_index("ix_lead_source_routes_provider", table_name="lead_source_routes")
    op.drop_table("lead_source_routes")
