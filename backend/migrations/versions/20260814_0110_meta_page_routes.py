"""Create meta_page_routes — public Page → tenant router for Meta lead webhooks.

Maps a Facebook page_id to its owning org + schema so an unauthenticated webhook
(Phase 2) can resolve the tenant before touching a tenant schema. Holds NO secrets.
UNIQUE page_id enforces "one Page ↔ one tenant" platform-wide. Public schema (shared).

Revision ID: 20260814_0110
Revises: 20260805_0109
Create Date: 2026-08-14 09:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260814_0110"
down_revision: str | None = "20260805_0109"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "meta_page_routes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("page_id", sa.String(64), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("schema_name", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
    )
    # unique=True + index=True on the model → a single UNIQUE index on page_id.
    op.create_index("ix_meta_page_routes_page_id", "meta_page_routes", ["page_id"], unique=True)
    op.create_index("ix_meta_page_routes_organization_id", "meta_page_routes", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_meta_page_routes_organization_id", table_name="meta_page_routes")
    op.drop_index("ix_meta_page_routes_page_id", table_name="meta_page_routes")
    op.drop_table("meta_page_routes")
