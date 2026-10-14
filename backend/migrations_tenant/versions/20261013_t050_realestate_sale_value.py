"""One-time catch-up: real-estate sales orders worth ₹0 get their booking's sale value.

A flat's lead keeps `value` at 0 (the field is hidden on the real-estate lead form) and Sold copied it into the sales
order, so every flat sold so far shows ₹0 in Finance → Sales Orders (and its auto-invoice is ₹0). From now on the order
takes the booking's agreed price (app/real_estate/sale_value.py). This fills in the orders already made, with the SAME
rule: the lead's live booking (confirmed before draft, newest first) — its saved box price; else its total less GST,
stamp duty and registration; else its unit's price.

Only touches orders that are worth exactly 0, belong to a real-estate lead and have such a booking; an order with no
booking stays as it is. A sale value of ₹1000 crore or more can't be stored (deal_value is NUMERIC(12,2)) — it is a
typo in the saved pricing, so that order is skipped and counted in the log (the app treats it the same way), rather
than failing the workspace's whole upgrade. Its invoice follows only when that invoice is also 0 and has no payment
recorded. Commission and brokerage already accrued (or not) for those sales are NOT re-worked here. Idempotent: a
second run finds no ₹0 orders with a booking (a skipped order is listed again). Downgrade leaves the filled-in values
(they are correct). Runs per tenant via the migration search_path.

Revision ID: 20261013_t050
Revises: 20261013_t049
Create Date: 2026-10-13 15:00:00.000000
"""

import logging
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text


revision: str = "20261013_t050"
down_revision: str | None = "20261013_t049"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

# sales_orders.deal_value / invoices.amount are NUMERIC(12,2): this value and above overflows them (the same bound as
# MAX_SALE_VALUE in app/real_estate/sale_value.py).
MAX_SALE_VALUE = "1e10"

# A JSON field as a number, or NULL when it isn't one (pricing snapshots are client-written JSON). A digit string too
# long to cast safely (Postgres numeric stops at about 131,000 digits) is read as a huge number of its sign — far
# over MAX_SALE_VALUE, as the app reads it — so it is skipped like any other too-large value instead of failing the
# upgrade.
_NUM = (
    "(CASE WHEN (b.pricing_snapshot ->> '{key}') ~ '^-?[0-9]+(\\.[0-9]+)?$' THEN"
    " CASE WHEN length(b.pricing_snapshot ->> '{key}') <= 1000 THEN (b.pricing_snapshot ->> '{key}')::numeric"
    " WHEN left(b.pricing_snapshot ->> '{key}', 1) = '-' THEN -1e1000 ELSE 1e1000 END"
    " END)"
)


def _num(key: str) -> str:
    return _NUM.format(key=key)


_SALE_VALUE = f"""
    CASE
        WHEN {_num('boxPrice')} > 0 THEN {_num('boxPrice')}
        WHEN {_num('total')} IS NOT NULL
             AND {_num('total')} - GREATEST(COALESCE({_num('gstAmount')}, 0), 0)
                 - GREATEST(COALESCE({_num('stampDutyAmount')}, 0), 0)
                 - GREATEST(COALESCE({_num('registrationAmount')}, 0), 0) > 0
            THEN {_num('total')} - GREATEST(COALESCE({_num('gstAmount')}, 0), 0)
                 - GREATEST(COALESCE({_num('stampDutyAmount')}, 0), 0)
                 - GREATEST(COALESCE({_num('registrationAmount')}, 0), 0)
        ELSE u.base_price
    END
"""


_PICKED = f"""
    WITH picked AS (
        SELECT DISTINCT ON (so.id) so.id AS order_id, ROUND(({_SALE_VALUE})::numeric, 2) AS sale_value
        FROM sales_orders so
        JOIN leads l ON l.id = so.lead_id
        JOIN bookings b ON b.lead_id = so.lead_id AND b.is_deleted = false AND b.status <> 'cancelled'
        JOIN units u ON u.id = b.unit_id
        WHERE so.deal_value = 0 AND so.is_deleted = false AND l.industry = 'real_estate'
        ORDER BY so.id, (b.status = 'confirmed') DESC, b.created_at DESC
    )
"""


def upgrade() -> None:
    conn = op.get_bind()
    # Orders whose value can't be stored: left at 0 and listed in the log, so the booking's pricing can be fixed.
    too_large = [
        str(row.order_id)
        for row in conn.execute(
            text(f"{_PICKED} SELECT order_id FROM picked WHERE sale_value >= {MAX_SALE_VALUE} ORDER BY order_id")
        ).fetchall()
    ]
    updated = conn.execute(
        text(
            f"""
            {_PICKED}
            UPDATE sales_orders so
            SET deal_value = picked.sale_value, updated_at = now()
            FROM picked
            WHERE so.id = picked.order_id AND picked.sale_value > 0 AND picked.sale_value < {MAX_SALE_VALUE}
            RETURNING so.id
            """
        )
    ).fetchall()
    invoices = 0
    if updated:
        invoices = conn.execute(
            text(
                """
                UPDATE invoices i
                SET amount = so.deal_value, updated_at = now()
                FROM sales_orders so
                WHERE i.sales_order_id = so.id
                  AND so.id = ANY(:ids)
                  AND i.amount = 0
                  AND NOT EXISTS (SELECT 1 FROM payments p WHERE p.invoice_id = i.id)
                """
            ),
            {"ids": [row.id for row in updated]},
        ).rowcount
    schema = conn.execute(text("SELECT current_schema()")).scalar()
    # The migration logger, so the counts land in the server log next to "Running upgrade …" for each workspace.
    skipped = f"skipped, sale value of 1000 crore or more: {len(too_large)}"
    if too_large:
        shown = ", ".join(too_large[:20]) + (f" (+{len(too_large) - 20} more)" if len(too_large) > 20 else "")
        skipped += f" (orders {shown})"
    logging.getLogger("alembic.runtime.migration").info(
        f"[t050] {schema}: real-estate sales orders filled from their booking: {len(updated)}; "
        f"invoices updated: {invoices}; {skipped}"
    )


def downgrade() -> None:
    # Data-only catch-up; the filled-in values are correct, so there is nothing to undo.
    pass
