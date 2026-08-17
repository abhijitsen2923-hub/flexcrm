"""Add OAuth fields to meta_connections — support the "Connect Facebook" flow.

Adds auth_type (byo|oauth), the long-lived user token + its expiry (oauth refresh),
the granted scopes, and the webhook subscription status. Existing rows default to
auth_type='byo' (unchanged behaviour). Per-tenant schema (search_path).

Revision ID: 20260814_t030
Revises: 20260805_t029
Create Date: 2026-08-14 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260814_t030"
down_revision: str | None = "20260805_t029"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "meta_connections",
        sa.Column("auth_type", sa.String(10), nullable=False, server_default=sa.text("'byo'")),
    )
    op.add_column("meta_connections", sa.Column("user_token_encrypted", sa.Text(), nullable=True))
    op.add_column(
        "meta_connections",
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("meta_connections", sa.Column("granted_scopes", sa.JSON(), nullable=True))
    op.add_column(
        "meta_connections",
        sa.Column("subscription_status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
    )


def downgrade() -> None:
    op.drop_column("meta_connections", "subscription_status")
    op.drop_column("meta_connections", "granted_scopes")
    op.drop_column("meta_connections", "token_expires_at")
    op.drop_column("meta_connections", "user_token_encrypted")
    op.drop_column("meta_connections", "auth_type")
