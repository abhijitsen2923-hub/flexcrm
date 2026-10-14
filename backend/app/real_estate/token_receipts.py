"""The token / booking amount as a real payment (t049).

A token is recorded on the booking (`Booking.token_*` — captured at the lead's "Booked / Token" move or with
PUT /bookings/{id}/token) and mirrored by exactly ONE PaymentReceipt with `is_token = true` (a partial unique index
enforces one per booking). So the token counts wherever receipts count — Paid till now, Customer Receivables, the
refund's gross paid — and it is counted once: updating the token edits that receipt, it never adds a second one.

The receipt is applied to the booking's first instalment:
- the plan's "on booking" row when the booking took a project payment plan;
- else the earliest-due row with nothing paid yet;
- else, when the booking has no rows at all, a "Booking amount" row (milestone_key "__token__", demand = token) is
  created and is fully paid by it;
- else (rows exist but all already carry money) it stays unapplied — still a receipt, so still counted as paid.

Money rules: the booking row is locked FOR NO KEY UPDATE first (the same lock as payment_plan.py — it serialises the
booking's money writes but still lets a payment insert a row referencing the booking), then the token receipt and the
booking's instalments FOR UPDATE. Other receipts are never touched. A cancelled booking's token is never changed (its
money was settled by the cancel / refund). Once the token receipt exists it is a recorded payment: changing its amount
or date needs FINANCE_RECORD_PAYMENT (accounts), like any other payment; its mode / reference stay editable.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, ConflictError
from app.core.logging import get_logger
from app.database.enums import BookingStatus
from app.real_estate.models import Booking, PaymentReceipt, PaymentSchedule
from app.real_estate.payment_plan import parse_plan
from app.real_estate.schemas import TOKEN_MILESTONE_KEY

logger = get_logger(__name__)

# The row created for a token when the booking has no instalments (milestone_key TOKEN_MILESTONE_KEY — a builder's
# plan can't use that key: schemas.check_payment_plan rejects it).
TOKEN_ROW_NAME = "Booking amount"
TOKEN_RECEIPT_NOTE = "Token / booking amount"
CANCELLED_TOKEN_MESSAGE = "This booking is cancelled — its token can't be changed."
# Changing it needs payment-recording permission AND access to the lead (owners and sales managers have both).
TOKEN_PAYMENT_MESSAGE = (
    "The token is a recorded payment — ask an owner or sales manager to change its amount or date."
)

_ZERO = Decimal("0")


def _cents(amount) -> Decimal:
    return Decimal(amount or 0).quantize(Decimal("0.01"))


def _settle(row: PaymentSchedule, today: date) -> None:
    """Outstanding + overdue after a row's demand or paid amount changed (same rule as record_payment)."""
    row.outstanding = max(_ZERO, (row.demand_amount or _ZERO) - (row.paid_amount or _ZERO))
    row.is_overdue = row.outstanding > 0 and row.due_date < today


async def lock_booking(session: AsyncSession, booking_id) -> BookingStatus | None:
    """Take the booking's money lock (FOR NO KEY UPDATE) — every token / plan / payment write takes it first.
    Returns the booking's status as committed once the lock is held (a cancel that won the race shows here)."""
    return await session.scalar(
        select(Booking.status).where(Booking.id == booking_id).with_for_update(key_share=True)
    )


async def token_receipt_for(session: AsyncSession, booking_id) -> PaymentReceipt | None:
    """The booking's token receipt, locked FOR UPDATE (the caller holds the booking lock)."""
    return (
        await session.scalars(
            select(PaymentReceipt)
            .where(PaymentReceipt.booking_id == booking_id, PaymentReceipt.is_token.is_(True))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).first()


async def _locked_rows(session: AsyncSession, booking_id) -> list[PaymentSchedule]:
    # Fixed order (by id) — the same order create_payment_plan locks them in.
    return list(
        (
            await session.scalars(
                select(PaymentSchedule)
                .where(PaymentSchedule.booking_id == booking_id)
                .order_by(PaymentSchedule.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
    )


def first_instalment(booking: Booking, rows: list[PaymentSchedule]) -> PaymentSchedule | None:
    """Which existing row the token pays: the plan's "on booking" row (plan order) if the booking took a project
    plan, else the earliest-due row with nothing paid yet. None = no such row."""
    by_key = {row.milestone_key: row for row in rows if row.milestone_key}
    for milestone in parse_plan(booking.payment_plan):
        if milestone.due_on == "on_booking" and milestone.key in by_key:
            return by_key[milestone.key]
    unpaid = [row for row in rows if (row.paid_amount or _ZERO) == 0]
    if not unpaid:
        return None
    return min(unpaid, key=lambda row: (row.due_date, str(row.id)))


def _apply(row: PaymentSchedule, receipt: PaymentReceipt, amount: Decimal, today: date) -> None:
    row.paid_amount = (row.paid_amount or _ZERO) + amount
    _settle(row, today)
    receipt.schedule_id = row.id


async def apply_token(
    session: AsyncSession, booking: Booking, receipt: PaymentReceipt, rows: list[PaymentSchedule], today: date
) -> PaymentSchedule | None:
    """Apply an UNAPPLIED token receipt to the booking's first instalment (module docstring); `rows` are the
    booking's instalments, already locked. Returns the row it was applied to (None = left unapplied)."""
    amount = receipt.amount or _ZERO
    target = first_instalment(booking, rows)
    if target is None and not rows:
        target = PaymentSchedule(
            booking_id=booking.id,
            installment_name=TOKEN_ROW_NAME,
            due_date=receipt.paid_on,
            demand_amount=amount,
            paid_amount=_ZERO,
            outstanding=amount,
            is_overdue=False,
            milestone_key=TOKEN_MILESTONE_KEY,
            percent=None,
        )
        session.add(target)
        await session.flush()  # the receipt points at the new row's id
    if target is None:
        logger.info("token receipt for booking %s left unapplied: every instalment already has money", booking.id)
        return None
    _apply(target, receipt, amount, today)
    return target


async def sync_token_receipt(
    session: AsyncSession, booking: Booking, *, can_record_payment: bool
) -> PaymentReceipt | None:
    """Create or update the booking's single token receipt from its token_* fields and apply / re-apply it.

    Call after setting the token fields, inside the caller's transaction (the caller commits; on an error it rolls
    back, token fields included). `can_record_payment`: the user holds FINANCE_RECORD_PAYMENT — needed to change an
    existing token receipt's amount or date (AuthorizationError otherwise). ConflictError when the booking was
    cancelled. Returns the receipt, or None when the booking has no token."""
    # The session doesn't autoflush: write the token fields (and a just-created booking / its plan rows) first so
    # the lock and the row queries below see them.
    await session.flush()
    if await lock_booking(session, booking.id) == BookingStatus.cancelled:
        # Re-checked under the lock: a cancel / refund that committed while this waited has settled the booking's
        # money without this token — a receipt added now would sit outside that settlement.
        raise ConflictError(CANCELLED_TOKEN_MESSAGE)
    amount = booking.token_amount
    if amount is None or amount <= 0:
        return None  # the API never clears a token (it must be > 0); nothing to mirror
    paid_on = booking.token_received_on or date.today()
    mode = booking.token_mode or "other"
    today = date.today()

    receipt = await token_receipt_for(session, booking.id)
    rows = await _locked_rows(session, booking.id)
    if receipt is None:
        receipt = PaymentReceipt(
            booking_id=booking.id,
            schedule_id=None,
            amount=amount,
            paid_on=paid_on,
            mode=mode,
            reference=booking.token_reference,
            notes=TOKEN_RECEIPT_NOTE,
            is_token=True,
        )
        session.add(receipt)
        await apply_token(session, booking, receipt, rows, today)
        await session.flush()
        return receipt

    # An update: the receipt follows the token; its row moves by the difference only. Notes are kept (a receipt
    # linked by the t049 catch-up keeps what staff wrote on it).
    previous = receipt.amount or _ZERO
    previous_on = receipt.paid_on
    if not can_record_payment and (_cents(amount) != _cents(previous) or paid_on != previous_on):
        # The token is a recorded payment now (accounts may have entered it): only someone who may record payments
        # changes how much was paid or when. Mode / reference are details and stay editable.
        raise AuthorizationError(TOKEN_PAYMENT_MESSAGE)
    receipt.amount = amount
    receipt.paid_on = paid_on
    receipt.mode = mode
    receipt.reference = booking.token_reference
    applied = next((row for row in rows if row.id == receipt.schedule_id), None)
    if applied is None:
        receipt.schedule_id = None
        await apply_token(session, booking, receipt, rows, today)
    else:
        applied.paid_amount = (applied.paid_amount or _ZERO) + (amount - previous)
        if applied.paid_amount < 0:
            # Only possible if the row was changed outside the API; never show negative money.
            logger.warning("token update would make row %s paid negative — clamped to 0", applied.id)
            applied.paid_amount = _ZERO
        if applied.milestone_key == TOKEN_MILESTONE_KEY and applied.demand_amount == previous:
            # The "Booking amount" row IS the token while it still mirrors it: its demand follows the token, and so
            # does its due date if that was the token's date. Once finance changed its demand the figures are
            # theirs — only the paid amount moves (and the outstanding with it).
            applied.demand_amount = amount
            if applied.due_date == previous_on:
                applied.due_date = paid_on
        _settle(applied, today)
    await session.flush()
    return receipt

