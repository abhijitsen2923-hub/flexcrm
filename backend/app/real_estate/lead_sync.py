"""Booking events move the buyer's lead forward (post-booking flow).

- a payment recorded on the booking (POST /bookings/{id}/payments — the token is never recorded there) →
  Agreement / Payment;
- the registration recorded (POST /bookings/{id}/register) → Registration;
- the possession checklist fully ticked (PUT /bookings/{id}/possession) → Possession.

Rules:
- forward only: never backward, never a closed (Sold / lost) lead, and skipped when the lead is already at or past
  the target — so a second payment never writes a second history row;
- only after Booked / Token: a lead that never reached it is left where it is (a booking event doesn't skip the
  token capture);
- only a move the user who recorded the event could make by hand: their role may set the target stage (can_set_stage
  — roles the stage rules leave unrestricted, like accounts recording a payment, may), and a front-line rep (assigned
  leads only) must own the lead. Otherwise it is skipped and logged — the write itself still stands;
- never Sold: closing stays a manager's click (AUTO_STAGE_TARGETS is the whole list);
- recorded as the SYSTEM (performed_by NULL). Commission re-attribution credits the people who moved a lead and skips a
  NULL performer (finance/services.py), so whoever recorded the money earns no assist from it; the comment names them;
- runs AFTER the caller's money write has committed, through the normal StageTransitionService (history row, cache
  wipe, realtime event). Any failure is rolled back and logged — it never fails or undoes the payment, the
  registration or the checklist that triggered it.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.core.permissions import ASSIGNED_ONLY_LEAD_ROLES, can_set_stage
from app.database.enums import BookingStatus, LeadIndustry, PipelineStageCategory
from app.models.lead import Lead
from app.real_estate.models import Booking
from app.repositories.pipeline_stages import PipelineStageRepository
from app.schemas.stage_transition import StageTransitionCreate

logger = get_logger(__name__)

BOOKED_STAGE = "booked"
AGREEMENT_PAYMENT_STAGE = "agreement_payment"
REGISTRATION_STAGE = "registration"
POSSESSION_STAGE = "possession"
# Every stage a booking event may move a lead to. Sold is deliberately not here.
AUTO_STAGE_TARGETS: frozenset[str] = frozenset({AGREEMENT_PAYMENT_STAGE, REGISTRATION_STAGE, POSSESSION_STAGE})

# The handover checklist has 7 items — POSSESSION_CHECKLIST in frontend/src/utils/purchaseProgress.ts, the list the
# Possession page and the Customer drawer tick (the backend stores only the ticks). Keep the two in step. Possession
# is complete when at least that many are saved and all are ticked.
POSSESSION_CHECKLIST_ITEMS = 7


def possession_complete(checklist) -> bool:
    return (
        isinstance(checklist, list)
        and len(checklist) >= POSSESSION_CHECKLIST_ITEMS
        and all(item is True for item in checklist)
    )


def format_inr(amount) -> str:
    """₹ with Indian digit grouping (₹5,00,000); paise only when the amount isn't whole."""
    try:
        value = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        return f"₹{amount}"
    sign = "-" if value < 0 else ""
    whole, _, paise = f"{abs(value):.2f}".partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        groups.insert(0, head)
        whole = ",".join(groups) + "," + tail
    return f"{sign}₹{whole}" + (f".{paise}" if paise != "00" else "")


def actor_name(user) -> str:
    """The recording user's name for an automatic move's comment (captured before any commit / rollback)."""
    if user is None:
        return "a team member"
    name = f"{getattr(user, 'first_name', '') or ''} {getattr(user, 'last_name', '') or ''}".strip()
    return name or getattr(user, "email", None) or "a team member"


def _unit(unit_number: str | None) -> str:
    return f"unit {unit_number}" if unit_number else "the unit"


def payment_comment(amount, unit_number: str | None, recorded_by: str) -> str:
    return f"Auto: {format_inr(amount)} received on {_unit(unit_number)} — recorded by {recorded_by}."


def registration_comment(unit_number: str | None, registration_number: str | None, recorded_by: str) -> str:
    deed = f" (registration no. {registration_number})" if registration_number else ""
    return f"Auto: {_unit(unit_number)} registered{deed} — recorded by {recorded_by}."


def possession_comment(unit_number: str | None, recorded_by: str) -> str:
    return f"Auto: possession handed over on {_unit(unit_number)} (checklist complete) — recorded by {recorded_by}."


async def _rollback(session: AsyncSession) -> None:
    try:
        await session.rollback()
    except Exception:  # noqa: BLE001 — the money write is already committed; nothing more to undo
        logger.warning("auto stage move: rollback failed", exc_info=True)


async def advance_lead_after(
    session: AsyncSession, booking_id: UUID, target_code: str, comment: str, *, actor
) -> bool:
    """Move the booking's lead forward to `target_code` (see the module docstring). `actor` is the user who recorded
    the event (None = nobody to check it against, so no move). Call only AFTER the caller has committed its own
    write: the move commits (or rolls back) on its own, and every ORM object loaded before it may be expired
    afterwards — re-read what the response needs. Never raises; True = the lead was moved."""
    if target_code not in AUTO_STAGE_TARGETS:
        logger.error("auto stage move: %r is not an automatic target — ignored", target_code)
        return False
    # Plain values now: a rollback below expires every ORM object in the session, the caller's user included.
    actor_id = getattr(actor, "id", None)
    actor_role = getattr(actor, "role", None)
    # Local import: the stage service imports the finance and real-estate modules.
    from app.services.stage_transitions import StageTransitionService

    lead_id = None
    try:
        booking = (
            await session.execute(
                select(Booking).where(Booking.id == booking_id).execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if booking is None or booking.is_deleted or booking.status == BookingStatus.cancelled:
            return False
        lead_id = booking.lead_id
        if lead_id is None:
            return False
        # Locked (as the stage service does), then judged: a second event racing this one waits here and then
        # sees the lead already moved, so it never writes a duplicate history row.
        lead = (
            await session.execute(
                select(Lead).where(Lead.id == lead_id).with_for_update().execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if lead is None or lead.is_deleted or lead.industry != LeadIndustry.real_estate:
            await _rollback(session)  # release the lock
            return False
        stages = PipelineStageRepository(session)
        current = await stages.find(lead.industry, lead.stage_code)
        target = await stages.find(lead.industry, target_code)
        booked = await stages.find(lead.industry, BOOKED_STAGE)
        if (
            current is None
            or target is None
            or booked is None
            or current.category != PipelineStageCategory.active
            or current.position >= target.position
        ):
            await _rollback(session)
            return False
        skip = None
        if current.position < booked.position:
            skip = f"the lead is at '{lead.stage_code}', before Booked / Token"
        elif actor_role is None or not can_set_stage(actor_role, target_code):
            skip = f"role {getattr(actor_role, 'value', actor_role)} can't set that stage"
        elif actor_role in ASSIGNED_ONLY_LEAD_ROLES and lead.assigned_to_id != actor_id:
            skip = "the lead isn't assigned to the user who recorded it"
        if skip is not None:
            await _rollback(session)
            logger.info(
                "auto stage move to %s skipped for booking %s (lead %s): %s", target_code, booking_id, lead_id, skip
            )
            return False
        await StageTransitionService(session).create_transition(
            lead.id,
            StageTransitionCreate(
                to_stage_code=target_code,
                comment=comment,
                # Carried over: the service copies it as given, and None would wipe the lead's pending follow-up.
                next_action_date=lead.next_action_date,
            ),
            # The system's move (performed_by NULL — no commission assist from it), checked under the role of the
            # user who recorded the event (already judged above).
            actor_id=None,
            actor_role=actor_role,
            allow_backward=False,
            intent_source="auto",
        )
        return True
    except (ValidationError, AuthorizationError, NotFoundError, ConflictError, SQLAlchemyError) as exc:
        await _rollback(session)
        logger.warning(
            "auto stage move to %s skipped for booking %s (lead %s): %s",
            target_code, booking_id, lead_id, getattr(exc, "detail", None) or exc,
        )
        return False
    except Exception:  # noqa: BLE001 — a failed move must never fail the payment / registration / checklist
        await _rollback(session)
        logger.exception("auto stage move to %s failed for booking %s (lead %s)", target_code, booking_id, lead_id)
        return False
