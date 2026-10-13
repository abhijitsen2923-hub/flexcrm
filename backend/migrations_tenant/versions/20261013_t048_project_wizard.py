"""Add Project wizard: flat types per tower, project-level pricing, parking prices per type, and a payment plan
whose milestones fall due on an event (on booking / N days after / a stage done / possession / registration).

All additive and nullable (or with a server default), so code from before this revision keeps working against it:
- projects: project_type, pricing_basis, floor_rise_rate/_basis/_from, plc_rate, amenities_rate (₹/sq ft —
  NOT the existing lump-sum amenities_charges), parking_prices {type: ₹}, payment_plan [milestones],
  milestones_reached [{key, tower_id, reached_on}].
- towers.layout: the tower's saved layout (unit-number prefix, flat types A/B/C…, shops/godowns), so Edit shows
  exactly what was set up instead of guessing from the units.
- units: flat_type ("A"), configuration ("2 BHK"), has_plc.
- bookings.payment_plan: the project plan as it was when the booking took it (the buyer's terms don't move when
  the builder edits the project later).
- payment_schedules: milestone_key + percent for rows a plan generated; one row per (booking, milestone) is
  enforced by a partial unique index so raising a milestone twice (double click, two tabs) can't double-bill.

Runs per tenant via the migration search_path.

Revision ID: 20261013_t048
Revises: 20261011_t047
Create Date: 2026-10-13 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20261013_t048"
down_revision: str | None = "20261011_t047"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("project_type", sa.String(32), nullable=True))
    op.add_column("projects", sa.Column("pricing_basis", sa.String(16), nullable=True))
    op.add_column("projects", sa.Column("floor_rise_rate", sa.Numeric(12, 2), nullable=True))
    op.add_column("projects", sa.Column("floor_rise_basis", sa.String(16), nullable=True))
    op.add_column("projects", sa.Column("floor_rise_from", sa.Integer(), nullable=True))
    op.add_column("projects", sa.Column("plc_rate", sa.Numeric(12, 2), nullable=True))
    op.add_column("projects", sa.Column("amenities_rate", sa.Numeric(12, 2), nullable=True))
    op.add_column("projects", sa.Column("parking_prices", sa.JSON(), nullable=True))
    op.add_column("projects", sa.Column("payment_plan", sa.JSON(), nullable=True))
    op.add_column("projects", sa.Column("milestones_reached", sa.JSON(), nullable=True))

    op.add_column("towers", sa.Column("layout", sa.JSON(), nullable=True))

    op.add_column("units", sa.Column("flat_type", sa.String(8), nullable=True))
    op.add_column("units", sa.Column("configuration", sa.String(32), nullable=True))
    op.add_column("units", sa.Column("has_plc", sa.Boolean(), nullable=False, server_default=sa.false()))

    op.add_column("bookings", sa.Column("payment_plan", sa.JSON(), nullable=True))

    op.add_column("payment_schedules", sa.Column("milestone_key", sa.String(40), nullable=True))
    op.add_column("payment_schedules", sa.Column("percent", sa.Numeric(7, 3), nullable=True))
    op.create_index(
        "uq_payment_schedules_booking_milestone",
        "payment_schedules",
        ["booking_id", "milestone_key"],
        unique=True,
        postgresql_where=sa.text("milestone_key IS NOT NULL"),
        sqlite_where=sa.text("milestone_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_payment_schedules_booking_milestone", table_name="payment_schedules")
    op.drop_column("payment_schedules", "percent")
    op.drop_column("payment_schedules", "milestone_key")
    op.drop_column("bookings", "payment_plan")
    op.drop_column("units", "has_plc")
    op.drop_column("units", "configuration")
    op.drop_column("units", "flat_type")
    op.drop_column("towers", "layout")
    for column in (
        "milestones_reached",
        "payment_plan",
        "parking_prices",
        "amenities_rate",
        "plc_rate",
        "floor_rise_from",
        "floor_rise_basis",
        "floor_rise_rate",
        "pricing_basis",
        "project_type",
    ):
        op.drop_column("projects", column)
