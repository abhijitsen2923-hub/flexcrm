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


def _number(value) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        return None
    return number if number.is_finite() else None


def booking_sale_value(pricing_snapshot, unit_price) -> Decimal:
    """The sale value from a booking's pricing snapshot (see the module docstring); 0 when nothing is known."""
    snap = pricing_snapshot if isinstance(pricing_snapshot, dict) else {}
    box = _number(snap.get("boxPrice"))
    if box is not None and box > 0:
        return box.quantize(_CENT)
    total = _number(snap.get("total"))
    if total is not None:
        taxes = sum(
            (max(_number(snap.get(key)) or Decimal("0"), Decimal("0")) for key in ("gstAmount", "stampDutyAmount", "registrationAmount")),
            Decimal("0"),
        )
        if total - taxes > 0:
            return (total - taxes).quantize(_CENT)
    price = _number(unit_price)
    return price.quantize(_CENT) if price is not None and price > 0 else Decimal("0")


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
