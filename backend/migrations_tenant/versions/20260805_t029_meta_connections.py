"""Create meta_connections — per-tenant Meta (Facebook/Instagram) Lead Ads connection.

Bring-your-own-token: stores the business's System-User token Fernet-encrypted plus
the page id, per-connection field mapping, per-form poll cursors, the owning
integration service user, and connection status. Per-tenant schema (search_path).
All FK references to public.users use the fully-qualified name so they resolve from
any tenant schema (mirrors the t001 pattern).

Revision ID: 20260805_t029
Revises: 20260805_t028
Create Date: 2026-08-05 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260805_t029"
down_revision: str | None = "20260805_t028"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "meta_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("page_id", sa.String(64), nullable=False),
        sa.Column("page_name", sa.String(255), nullable=True),
        sa.Column("token_encrypted", sa.Text(), nullable=False),
        sa.Column("default_industry", sa.String(20), nullable=False),
        sa.Column("field_map", sa.JSON(), nullable=True),
        sa.Column("form_cursors", sa.JSON(), nullable=True),
        sa.Column("integration_user_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("status_detail", sa.String(500), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "page_id", name="uq_meta_connections_provider_page"),
        sa.ForeignKeyConstraint(["created_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deleted_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["integration_user_id"], ["public.users.id"], ondelete="SET NULL"),
    )
    # Indexes implied by the audit/soft-delete mixins (parity with other tenant tables).
    op.create_index("ix_meta_connections_created_by_id", "meta_connections", ["created_by_id"])
    op.create_index("ix_meta_connections_updated_by_id", "meta_connections", ["updated_by_id"])
    op.create_index("ix_meta_connections_is_deleted", "meta_connections", ["is_deleted"])
    op.create_index("ix_meta_connections_deleted_at", "meta_connections", ["deleted_at"])
    op.create_index("ix_meta_connections_deleted_by_id", "meta_connections", ["deleted_by_id"])


def downgrade() -> None:
    op.drop_index("ix_meta_connections_deleted_by_id", table_name="meta_connections")
    op.drop_index("ix_meta_connections_deleted_at", table_name="meta_connections")
    op.drop_index("ix_meta_connections_is_deleted", table_name="meta_connections")
    op.drop_index("ix_meta_connections_updated_by_id", table_name="meta_connections")
    op.drop_index("ix_meta_connections_created_by_id", table_name="meta_connections")
    op.drop_table("meta_connections")
