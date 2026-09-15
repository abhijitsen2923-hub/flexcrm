"""Create call_agent_mappings — manual caller→user overrides for Callyzer attribution.

One row per (provider, emp_key = normalised last-10 device digits) pinning a device number
to a FlexCRM user. Per-tenant schema (search_path); FKs to public.users are fully qualified.

Revision ID: 20260915_t042
Revises: 20260915_t041
Create Date: 2026-09-15 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260915_t042"
down_revision: str | None = "20260915_t041"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "call_agent_mappings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("emp_key", sa.String(16), nullable=False),
        sa.Column("emp_number", sa.String(32), nullable=True),
        sa.Column("emp_name", sa.String(160), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "emp_key", name="uq_call_agent_mappings_provider_emp_key"),
        sa.ForeignKeyConstraint(["user_id"], ["public.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["public.users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_call_agent_mappings_emp_key", "call_agent_mappings", ["emp_key"])


def downgrade() -> None:
    op.drop_index("ix_call_agent_mappings_emp_key", table_name="call_agent_mappings")
    op.drop_table("call_agent_mappings")
