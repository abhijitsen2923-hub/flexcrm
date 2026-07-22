"""Add real-estate Project detail + default box-price columns (Phase B).

Enriches `projects` with declared specs (pin_code, landmark, tower/floor/flat/
garage counts, garage_options) and default box-price components (rate_a/b/c per
sqft by unit type, parking/legal/overhead/other/sinking/amenities costs). The
defaults seed the booking PriceCalculator so a new booking pre-fills from the
project instead of every field starting at ₹0. All columns are nullable and
additive — existing projects/bookings are unaffected.

Revision ID: 20260722_t019
Revises: 20260722_t018
Create Date: 2026-07-22 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260722_t019"
down_revision: str | None = "20260722_t018"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


# name, column-type factory — kept as a list so upgrade/downgrade stay in sync.
_COLUMNS = [
    ("pin_code", sa.String(12)),
    ("landmark", sa.String(255)),
    ("total_towers", sa.Integer()),
    ("total_floors", sa.Integer()),
    ("flats_per_floor", sa.Integer()),
    ("total_garages", sa.Integer()),
    ("garage_options", sa.JSON()),
    ("rate_a", sa.Numeric(12, 2)),
    ("rate_b", sa.Numeric(12, 2)),
    ("rate_c", sa.Numeric(12, 2)),
    ("parking_cost", sa.Numeric(14, 2)),
    ("legal_fees", sa.Numeric(14, 2)),
    ("overhead_cost", sa.Numeric(14, 2)),
    ("other_charges", sa.Numeric(14, 2)),
    ("sinking_fund", sa.Numeric(14, 2)),
    ("amenities_charges", sa.Numeric(14, 2)),
]


def upgrade() -> None:
    for name, coltype in _COLUMNS:
        op.add_column("projects", sa.Column(name, coltype, nullable=True))


def downgrade() -> None:
    for name, _ in reversed(_COLUMNS):
        op.drop_column("projects", name)
