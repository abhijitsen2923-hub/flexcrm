"""Create callyzer_connections + external_calls — per-tenant Callyzer call-tracking.

`callyzer_connections`: one per tenant; stores the Callyzer API token Fernet-encrypted
plus poll status/high-water marks. `external_calls`: synced call records (idempotent on
provider+external_id), matched to leads by `client_number_key` at read time; recordings
are linked via `recording_url` (never stored). Per-tenant schema (search_path); FK
references to public.users use the fully-qualified name so they resolve from any schema.

Revision ID: 20260914_t040
Revises: 20260905_t039
Create Date: 2026-09-14 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260914_t040"
down_revision: str | None = "20260905_t039"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "callyzer_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
        sa.Column("label", sa.String(120), nullable=True),
        sa.Column("token_encrypted", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), server_default=sa.text("'ok'"), nullable=False),
        sa.Column("status_detail", sa.String(500), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_call_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["created_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deleted_by_id"], ["public.users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_callyzer_connections_created_by_id", "callyzer_connections", ["created_by_id"])
    op.create_index("ix_callyzer_connections_updated_by_id", "callyzer_connections", ["updated_by_id"])
    op.create_index("ix_callyzer_connections_is_deleted", "callyzer_connections", ["is_deleted"])
    op.create_index("ix_callyzer_connections_deleted_at", "callyzer_connections", ["deleted_at"])
    op.create_index("ix_callyzer_connections_deleted_by_id", "callyzer_connections", ["deleted_by_id"])

    op.create_table(
        "external_calls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("external_id", sa.String(128), nullable=False),
        sa.Column("client_number", sa.String(32), nullable=True),
        sa.Column("client_number_key", sa.String(16), nullable=True),
        sa.Column("client_name", sa.String(160), nullable=True),
        sa.Column("emp_number", sa.String(32), nullable=True),
        sa.Column("emp_name", sa.String(160), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("call_type", sa.String(20), nullable=True),
        sa.Column("call_method", sa.String(20), nullable=True),
        sa.Column("call_mode", sa.String(20), nullable=True),
        sa.Column("provider_lead_id", sa.String(128), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("call_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("crm_status", sa.String(64), nullable=True),
        sa.Column("reminder_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recording_url", sa.Text(), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "external_id", name="uq_external_calls_provider_external_id"),
        sa.ForeignKeyConstraint(["user_id"], ["public.users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_external_calls_client_number_key", "external_calls", ["client_number_key"])
    op.create_index("ix_external_calls_call_at", "external_calls", ["call_at"])


def downgrade() -> None:
    op.drop_index("ix_external_calls_call_at", table_name="external_calls")
    op.drop_index("ix_external_calls_client_number_key", table_name="external_calls")
    op.drop_table("external_calls")
    op.drop_index("ix_callyzer_connections_deleted_by_id", table_name="callyzer_connections")
    op.drop_index("ix_callyzer_connections_deleted_at", table_name="callyzer_connections")
    op.drop_index("ix_callyzer_connections_is_deleted", table_name="callyzer_connections")
    op.drop_index("ix_callyzer_connections_updated_by_id", table_name="callyzer_connections")
    op.drop_index("ix_callyzer_connections_created_by_id", table_name="callyzer_connections")
    op.drop_table("callyzer_connections")
