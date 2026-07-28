"""Add units.carpet_area + built_up_area (area breakdown).

`units.area` stays the Super built-up (saleable) area used for pricing/display;
Carpet and Built-up are additional captured measures. Both nullable + additive.

Revision ID: 20260728_t025
Revises: 20260728_t024
Create Date: 2026-07-28 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260728_t025"
down_revision: str | None = "20260728_t024"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("units", sa.Column("carpet_area", sa.Numeric(10, 2), nullable=True))
    op.add_column("units", sa.Column("built_up_area", sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("units", "built_up_area")
    op.drop_column("units", "carpet_area")
