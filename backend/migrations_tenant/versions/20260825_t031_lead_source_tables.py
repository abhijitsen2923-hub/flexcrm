"""Create lead_source_connections + lead_source_deliveries — inbound push-portal ingest.

Per-tenant tables for portals that PUSH leads to us (99acres, later MagicBricks/Housing).
`lead_source_connections` = tenant config + status (the credential lives as a token hash in the
public lead_source_routes, not here). `lead_source_deliveries` = the persist-first raw log that
makes push-only ingest safe + replayable. Per-tenant schema (search_path); FKs to public.users
are fully-qualified so they resolve from any tenant schema (mirrors t029).

Revision ID: 20260825_t031
Revises: 20260814_t030
Create Date: 2026-08-25 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260825_t031"
down_revision: str | None = "20260814_t030"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lead_source_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("external_account_id", sa.String(64), nullable=True),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("default_industry", sa.String(20), nullable=False),
        sa.Column("field_map", sa.JSON(), nullable=True),
        sa.Column("integration_user_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("status_detail", sa.String(500), nullable=True),
        sa.Column("last_lead_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["created_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deleted_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["integration_user_id"], ["public.users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_lead_source_connections_created_by_id", "lead_source_connections", ["created_by_id"])
    op.create_index("ix_lead_source_connections_updated_by_id", "lead_source_connections", ["updated_by_id"])
    op.create_index("ix_lead_source_connections_is_deleted", "lead_source_connections", ["is_deleted"])
    op.create_index("ix_lead_source_connections_deleted_at", "lead_source_connections", ["deleted_at"])
    op.create_index("ix_lead_source_connections_deleted_by_id", "lead_source_connections", ["deleted_by_id"])

    op.create_table(
        "lead_source_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=True),
        sa.Column("external_id", sa.String(128), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), server_default=sa.text("'received'"), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lead_source_deliveries_connection_id", "lead_source_deliveries", ["connection_id"])
    op.create_index("ix_lead_source_deliveries_external_id", "lead_source_deliveries", ["external_id"])
    op.create_index("ix_lead_source_deliveries_status", "lead_source_deliveries", ["status"])


def downgrade() -> None:
    op.drop_index("ix_lead_source_deliveries_status", table_name="lead_source_deliveries")
    op.drop_index("ix_lead_source_deliveries_external_id", table_name="lead_source_deliveries")
    op.drop_index("ix_lead_source_deliveries_connection_id", table_name="lead_source_deliveries")
    op.drop_table("lead_source_deliveries")
    op.drop_index("ix_lead_source_connections_deleted_by_id", table_name="lead_source_connections")
    op.drop_index("ix_lead_source_connections_deleted_at", table_name="lead_source_connections")
    op.drop_index("ix_lead_source_connections_is_deleted", table_name="lead_source_connections")
    op.drop_index("ix_lead_source_connections_updated_by_id", table_name="lead_source_connections")
    op.drop_index("ix_lead_source_connections_created_by_id", table_name="lead_source_connections")
    op.drop_table("lead_source_connections")
