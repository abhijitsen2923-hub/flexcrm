"""Lead-first creation flow with auto-promote on Sold.

Adds contact fields (contact_name, contact_email, contact_phone, company_name)
directly to the Lead so prospects can be captured without a pre-existing
Customer. `leads.customer_id` becomes nullable. The Customer gets a new
`source_lead_id` column pointing back at the lead it was promoted from.

Migration is additive — no data wipe. Existing leads keep their customer_id
linkage; their contact_name is backfilled from `customers.contact_name`.

Revision ID: 20260522_0004
Revises: 20260521_0003
Create Date: 2026-05-22 10:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260522_0004"
down_revision: str | None = "20260521_0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # --- leads: relax customer_id, add contact fields ---------------------
    op.alter_column("leads", "customer_id", nullable=True)

    # Add contact_name as nullable first so we can backfill it from the
    # existing customer linkage; then promote to NOT NULL.
    op.add_column("leads", sa.Column("contact_name", sa.String(length=255), nullable=True))
    op.add_column("leads", sa.Column("contact_email", sa.String(length=255), nullable=True))
    op.add_column("leads", sa.Column("contact_phone", sa.String(length=32), nullable=True))
    op.add_column("leads", sa.Column("company_name", sa.String(length=255), nullable=True))

    # Backfill from the linked customer; fall back to the lead title if no
    # customer was attached (shouldn't happen with the prior schema, but the
    # COALESCE keeps the NOT NULL promotion safe).
    op.execute(
        """
        UPDATE leads
        SET contact_name = COALESCE(customers.contact_name, leads.title),
            contact_email = customers.email,
            contact_phone = customers.phone,
            company_name = customers.company_name
        FROM customers
        WHERE leads.customer_id = customers.id
        """
    )
    # Any leads with no customer get the title as contact_name.
    op.execute(
        "UPDATE leads SET contact_name = title WHERE contact_name IS NULL"
    )

    op.alter_column("leads", "contact_name", nullable=False)
    op.create_index("ix_leads_contact_email", "leads", ["contact_email"])

    # --- customers: add source_lead_id ------------------------------------
    op.add_column("customers", sa.Column("source_lead_id", sa.Uuid(), nullable=True))
    op.create_index("ix_customers_source_lead_id", "customers", ["source_lead_id"])
    op.create_foreign_key(
        "fk_customers_source_lead",
        "customers",
        "leads",
        ["source_lead_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_customers_source_lead", "customers", type_="foreignkey")
    op.drop_index("ix_customers_source_lead_id", table_name="customers")
    op.drop_column("customers", "source_lead_id")

    op.drop_index("ix_leads_contact_email", table_name="leads")
    op.drop_column("leads", "company_name")
    op.drop_column("leads", "contact_phone")
    op.drop_column("leads", "contact_email")
    op.drop_column("leads", "contact_name")
    op.alter_column("leads", "customer_id", nullable=False)
