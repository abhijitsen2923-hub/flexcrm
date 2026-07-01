"""Real estate tenant tables + lead column extensions.

Adds:
  - 6 real-estate columns to `leads`
  - `projects`, `towers`, `units`
  - `site_visits`
  - `bookings`, `booking_kyc_docs`, `payment_schedules`
  - `customer_documents`, `service_requests`

All new enum types (`unit_status_enum`, `booking_status_enum`,
`site_visit_feedback_enum`) were created in the public schema by migration
0102 and are referenced here with `create_type=False`.

Revision ID: 20260623_t002
Revises: 20260623_t001
Create Date: 2026-06-23 14:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260623_t002"
down_revision: str | None = "20260623_t001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # --- leads: add real-estate columns ------------------------------------
    op.add_column("leads", sa.Column("property_type", sa.String(64), nullable=True))
    op.add_column("leads", sa.Column("budget_min", sa.Numeric(14, 2), nullable=True))
    op.add_column("leads", sa.Column("budget_max", sa.Numeric(14, 2), nullable=True))
    op.add_column("leads", sa.Column("preferred_location", sa.String(255), nullable=True))
    op.add_column("leads", sa.Column("possession_preference", sa.String(64), nullable=True))
    op.add_column("leads", sa.Column("notes", sa.Text(), nullable=True))

    # --- projects -----------------------------------------------------------
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("builder_name", sa.String(255), nullable=False),
        sa.Column("location", sa.String(255), nullable=False),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("rera_number", sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- towers -------------------------------------------------------------
    op.create_table(
        "towers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("total_floors", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_towers_project_id", "towers", ["project_id"])

    # --- units --------------------------------------------------------------
    op.create_table(
        "units",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("tower_id", sa.Uuid(), nullable=False),
        sa.Column("floor", sa.Integer(), nullable=False),
        sa.Column("unit_number", sa.String(20), nullable=False),
        sa.Column("area", sa.Numeric(10, 2), nullable=False),
        sa.Column("area_unit", sa.String(20), nullable=False, server_default="sqft"),
        sa.Column("facing", sa.String(50), nullable=True),
        sa.Column("view", sa.String(100), nullable=True),
        sa.Column("base_price", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM("available", "reserved", "booked", "sold", name="unit_status_enum", create_type=False, schema="public"),
            nullable=False,
            server_default="available",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tower_id"], ["towers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_units_project_id", "units", ["project_id"])
    op.create_index("ix_units_tower_id", "units", ["tower_id"])
    op.create_index("ix_units_project_status", "units", ["project_id", "status"])
    op.create_index("ix_units_tower_floor", "units", ["tower_id", "floor"])

    # --- site_visits --------------------------------------------------------
    op.create_table(
        "site_visits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assigned_to_id", sa.Uuid(), nullable=True),
        sa.Column(
            "feedback",
            postgresql.ENUM("hot", "warm", "cold", name="site_visit_feedback_enum", create_type=False, schema="public"),
            nullable=True,
        ),
        sa.Column("attended", sa.Boolean(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_to_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_site_visits_project_scheduled", "site_visits", ["project_id", "scheduled_at"])
    op.create_index("ix_site_visits_lead_id", "site_visits", ["lead_id"])
    op.create_index("ix_site_visits_assigned_to_id", "site_visits", ["assigned_to_id"])
    op.create_index("ix_site_visits_scheduled_at", "site_visits", ["scheduled_at"])

    # --- bookings -----------------------------------------------------------
    op.create_table(
        "bookings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Uuid(), nullable=True),
        sa.Column("unit_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("step", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "status",
            postgresql.ENUM("draft", "confirmed", "cancelled", name="booking_status_enum", create_type=False, schema="public"),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("pricing_snapshot", sa.JSON(), nullable=True),
        sa.Column("scheduled_date", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deleted_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bookings_unit", "bookings", ["unit_id"])
    op.create_index("ix_bookings_customer", "bookings", ["customer_id"])
    op.create_index("ix_bookings_lead_id", "bookings", ["lead_id"])
    op.create_index("ix_bookings_is_deleted", "bookings", ["is_deleted"])

    # --- booking_kyc_docs ---------------------------------------------------
    op.create_table(
        "booking_kyc_docs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("doc_type", sa.String(64), nullable=False),
        sa.Column("file_path", sa.String(512), nullable=True),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_booking_kyc_docs_booking_id", "booking_kyc_docs", ["booking_id"])

    # --- payment_schedules --------------------------------------------------
    op.create_table(
        "payment_schedules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("installment_name", sa.String(120), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("demand_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("paid_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("outstanding", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("is_overdue", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payment_schedules_booking_id", "payment_schedules", ["booking_id"])
    op.create_index("ix_payment_schedules_booking_due_date", "payment_schedules", ["booking_id", "due_date"])

    # --- customer_documents -------------------------------------------------
    op.create_table(
        "customer_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("file_path", sa.String(512), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_customer_documents_customer", "customer_documents", ["customer_id"])

    # --- service_requests ---------------------------------------------------
    op.create_table(
        "service_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resolved_by_id"], ["public.users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_service_requests_customer_status", "service_requests", ["customer_id", "status"])
    op.create_index("ix_service_requests_customer_id", "service_requests", ["customer_id"])


def downgrade() -> None:
    op.drop_table("service_requests")
    op.drop_table("customer_documents")
    op.drop_table("payment_schedules")
    op.drop_table("booking_kyc_docs")
    op.drop_table("bookings")
    op.drop_table("site_visits")
    op.drop_table("units")
    op.drop_table("towers")
    op.drop_table("projects")
    for col in ("notes", "possession_preference", "preferred_location", "budget_max", "budget_min", "property_type"):
        op.drop_column("leads", col)
