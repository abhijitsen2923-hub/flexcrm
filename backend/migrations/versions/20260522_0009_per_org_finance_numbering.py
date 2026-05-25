"""Per-org uniqueness for sales_orders.order_number and invoices.invoice_number.

Same problem class as migration 0007 (leads/customers): the original
constraints were globally unique, so Org A and Org B couldn't both have
"SO-1001". Swap to composite uniqueness on (organization_id, …).

Revision ID: 20260522_0009
Revises: 20260522_0008
Create Date: 2026-05-22 19:00:00.000000
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260522_0009"
down_revision: str | None = "20260522_0008"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_sales_orders_order_number", "sales_orders", type_="unique")
    op.create_unique_constraint(
        "uq_sales_orders_org_order_number",
        "sales_orders",
        ["organization_id", "order_number"],
    )
    op.drop_constraint("uq_invoices_invoice_number", "invoices", type_="unique")
    op.create_unique_constraint(
        "uq_invoices_org_invoice_number",
        "invoices",
        ["organization_id", "invoice_number"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_invoices_org_invoice_number", "invoices", type_="unique")
    op.create_unique_constraint("uq_invoices_invoice_number", "invoices", ["invoice_number"])
    op.drop_constraint("uq_sales_orders_org_order_number", "sales_orders", type_="unique")
    op.create_unique_constraint("uq_sales_orders_order_number", "sales_orders", ["order_number"])
