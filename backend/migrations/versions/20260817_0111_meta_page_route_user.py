"""Add meta_page_routes.provider_user_id — route Meta deauth/data-deletion by FB user.

Meta's deauthorize + data-deletion callbacks arrive with only a Facebook user_id (no
page_id). This public, cross-tenant, indexed column lets those callbacks find every Page
a given user connected — across all workspaces — without scanning tenant schemas. NULL for
bring-your-own-token routes (only OAuth connections attribute a granting user). Public.

Revision ID: 20260817_0111
Revises: 20260814_0110
Create Date: 2026-08-17 09:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260817_0111"
down_revision: str | None = "20260814_0110"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "meta_page_routes",
        sa.Column("provider_user_id", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_meta_page_routes_provider_user_id", "meta_page_routes", ["provider_user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_meta_page_routes_provider_user_id", table_name="meta_page_routes")
    op.drop_column("meta_page_routes", "provider_user_id")
