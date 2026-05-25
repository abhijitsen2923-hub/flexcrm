"""Per-org lead_number and customer_number uniqueness.

Migration 0006 added `organization_id` everywhere but left the
`leads.lead_number` and `customers.customer_number` constraints as GLOBAL
uniques — meaning two orgs couldn't both start their lead numbering at
89001. Swap the global constraint for a composite `(organization_id,
lead_number)` so each org maintains its own sequence.

Revision ID: 20260522_0007
Revises: 20260522_0006
Create Date: 2026-05-22 17:00:00.000000
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260522_0007"
down_revision: str | None = "20260522_0006"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_leads_lead_number", "leads", type_="unique")
    op.create_unique_constraint(
        "uq_leads_org_lead_number", "leads", ["organization_id", "lead_number"]
    )
    op.drop_constraint("uq_customers_customer_number", "customers", type_="unique")
    op.create_unique_constraint(
        "uq_customers_org_customer_number",
        "customers",
        ["organization_id", "customer_number"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_customers_org_customer_number", "customers", type_="unique")
    op.create_unique_constraint(
        "uq_customers_customer_number", "customers", ["customer_number"]
    )
    op.drop_constraint("uq_leads_org_lead_number", "leads", type_="unique")
    op.create_unique_constraint("uq_leads_lead_number", "leads", ["lead_number"])
