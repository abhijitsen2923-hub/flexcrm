"""Add leads.salutation (Mr / Mrs / Ms / Master) — contact honorific.

Revision ID: 20260722_t018
Revises: 20260715_t017
Create Date: 2026-07-22 10:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260722_t018"
down_revision: str | None = "20260715_t017"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("salutation", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("leads", "salutation")
