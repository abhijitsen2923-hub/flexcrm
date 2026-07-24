"""Add customers.sale_value — deal value snapshotted at close (Phase C4).

Point-in-time snapshot of the source lead's deal value, captured when a lead is
promoted to a Customer on Sold. Distinct from `ltv` (a running aggregate of
confirmed bookings/deals/renewals). Nullable + additive.

Revision ID: 20260724_t022
Revises: 20260723_t021
Create Date: 2026-07-24 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260724_t022"
down_revision: str | None = "20260723_t021"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("sale_value", sa.Numeric(14, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("customers", "sale_value")
