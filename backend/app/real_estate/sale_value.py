"""What a real-estate sale is worth — the value a Sold deal's sales order (and with it the partner's brokerage and the
salesperson's sales credit) is worked out on.

It is the booking's agreed price BEFORE GST, stamp duty and registration (those are tax / government charges, not the
builder's revenue): from the booking's saved pricing, its box price; else its total less GST, stamp duty and
registration; else — no price worked out yet — the unit's price. Real-estate leads keep their own `value` at 0 (the
field is hidden on the lead form), so without this every flat's sales order was worth ₹0.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.enums import BookingStatus
from app.real_estate.models import Booking, Unit

_CENT = Decimal("0.01")
# sales_orders.deal_value (and its invoice's amount) is NUMERIC(12,2): ₹1000 crore or more can't be stored. Such a
# figure is a typo in the saved pricing, so the sale is treated as having no price (₹0, as with no booking) rather than
# failing the Sold move. Migration t050 skips the same orders.
MAX_SALE_VALUE = Decimal("1e10")


def _number(value) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        return None
    return number if number.is_finite() else None


def booking_sale_value(pricing_snapshot, unit_price) -> Decimal:
    """The sale value from a booking's pricing snapshot (see the module docstring); 0 when nothing is known, or when
    the value is too large to store (MAX_SALE_VALUE)."""
    try:
        value = _raw_sale_value(pricing_snapshot, unit_price)
    except ArithmeticError:
        # A figure too large even to subtract (e.g. "1e1000000" in the saved total) — a typo, like any value over
        # MAX_SALE_VALUE; it must not fail the Sold move.
        return Decimal("0")
    # Compared before rounding too: quantize() itself fails on a number this large.
    if value is None or value >= MAX_SALE_VALUE:
        return Decimal("0")
    value = value.quantize(_CENT)
    return value if value < MAX_SALE_VALUE else Decimal("0")


def _raw_sale_value(pricing_snapshot, unit_price) -> Decimal | None:
    snap = pricing_snapshot if isinstance(pricing_snapshot, dict) else {}
    box = _number(snap.get("boxPrice"))
    if box is not None and box > 0:
        return box
    total = _number(snap.get("total"))
    if total is not None:
        taxes = sum(
            (max(_number(snap.get(key)) or Decimal("0"), Decimal("0")) for key in ("gstAmount", "stampDutyAmount", "registrationAmount")),
            Decimal("0"),
        )
        if total - taxes > 0:
            return total - taxes
    price = _number(unit_price)
    return price if price is not None and price > 0 else None


async def sale_value_for_lead(session: AsyncSession, lead_id: UUID) -> Decimal:
    """The sale value of the lead's booking — its live (not cancelled) one, a confirmed booking before a draft,
    newest first. 0 when the lead has no booking."""
    row = (
        await session.execute(
            select(Booking.pricing_snapshot, Unit.base_price)
            .join(Unit, Booking.unit_id == Unit.id)
            .where(
                Booking.lead_id == lead_id,
                Booking.is_deleted.is_(False),
                Booking.status != BookingStatus.cancelled,
            )
            .order_by(case((Booking.status == BookingStatus.confirmed, 0), else_=1), Booking.created_at.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        return Decimal("0")
    return booking_sale_value(row.pricing_snapshot, row.base_price)
