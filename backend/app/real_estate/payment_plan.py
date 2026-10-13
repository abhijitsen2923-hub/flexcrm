"""A project's payment plan → each booking's demands (t048).

The builder's plan is a list of milestones (their own names), each a % of the booking's price and due either on
a date the booking fixes (on booking / N days after / a calendar date) or on an EVENT (a construction stage done,
possession, registration). A booking keeps its own copy of the plan (`Booking.payment_plan` — the buyer's terms
don't move when the builder edits the project later) and gets one PaymentSchedule row per milestone, tagged with
the milestone's key and %:
- date milestones get their row as soon as the booking takes the plan;
- an event milestone has NO row (it is "pending") until the builder marks it reached on the project — for the
  whole project or per tower — or raises it on one booking. A booking made after the mark gets it straight away.

Money rules: one row per (booking, milestone) is enforced by a unique index, so a double click / two tabs can't
double-bill; rows are locked before they change; a row that has a payment, a receipt or a live invoice is never
re-priced or removed.
"""
from __future__ import annotations

import copy
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import NamedTuple
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissions
from app.core.logging import get_logger
from app.core.permissions import PermissionCode
from app.database.enums import BookingStatus
from app.database.session import get_db_session
from app.real_estate.models import Booking, BookingInvoice, PaymentReceipt, PaymentSchedule, Project, Tower, Unit
from app.real_estate.schemas import (
    EVENT_DUE_ON,
    BookingRead,
    MilestoneRaise,
    MilestoneReachedCreate,
    MilestoneReachedResult,
    MilestoneUndoResult,
    ProjectRead,
)

logger = get_logger(__name__)

router = APIRouter()

_CENT = Decimal("0.01")
# PaymentSchedule.percent is NUMERIC(7,3): a row's amount is always worked out from the % exactly as stored, so a
# later re-price gives the same figure the row was created with.
_PERCENT_STEP = Decimal("0.001")
_ZERO = Decimal("0")


# ---------------------------------------------------------------------------
# Price + milestones
# ---------------------------------------------------------------------------

def _number(value) -> Decimal | None:
    """A pricing-snapshot figure as a Decimal; None when it is missing or not a finite number."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        return None
    return number if number.is_finite() else None


def plan_base(booking: Booking, unit: Unit | None = None) -> Decimal:
    """What the plan's percentages are a share of: the booking's price — box price + GST, not stamp duty or
    registration (those go to the government, not the builder).

    From the saved pricing snapshot: boxPrice + gstAmount; else total − stamp duty − registration; else (no price
    worked out yet) the unit's base price. `unit` falls back to booking.unit only when it is already loaded — an
    async session must never lazy-load."""
    snap = booking.pricing_snapshot if isinstance(booking.pricing_snapshot, dict) else {}
    box, gst = _number(snap.get("boxPrice")), _number(snap.get("gstAmount"))
    if box is not None and gst is not None and box > 0 and gst >= 0:
        return (box + gst).quantize(_CENT)
    total = _number(snap.get("total"))
    if total is not None:
        stamp = _number(snap.get("stampDutyAmount")) or _ZERO
        registration = _number(snap.get("registrationAmount")) or _ZERO
        base = total - max(stamp, _ZERO) - max(registration, _ZERO)
        if base > 0:
            return base.quantize(_CENT)
    if unit is None:
        unit = booking.__dict__.get("unit")
    price = _number(unit.base_price) if unit is not None else None
    return price.quantize(_CENT) if price is not None and price > 0 else _ZERO


def demand_for(percent: Decimal, base: Decimal) -> Decimal:
    return (base * percent / Decimal(100)).quantize(_CENT, rounding=ROUND_HALF_UP)


class Milestone(NamedTuple):
    key: str
    label: str
    percent: Decimal
    due_on: str
    days: int | None
    due_date: date | None


def parse_plan(plan) -> list[Milestone]:
    """The billable milestones of a stored plan (project or booking copy). Plans are validated when written, so
    this only skips an entry that is somehow malformed instead of failing the booking over it."""
    milestones: list[Milestone] = []
    for raw in plan or []:
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("key") or "").strip()
        percent = _number(raw.get("percent"))
        due_on = str(raw.get("due_on") or "")
        if not key or percent is None or percent <= 0 or percent > 100 or not due_on:
            logger.warning("payment plan: skipping malformed milestone %r", raw)
            continue
        try:
            days = int(raw["days"]) if raw.get("days") is not None and not isinstance(raw["days"], bool) else None
        except (TypeError, ValueError):
            days = None
        due_date = None
        if raw.get("due_date"):
            try:
                due_date = date.fromisoformat(str(raw["due_date"])[:10])
            except ValueError:
                due_date = None
        label = str(raw.get("label") or "").strip() or "Installment"
        milestones.append(
            Milestone(
                key=key[:40],
                label=label[:120],
                percent=percent.quantize(_PERCENT_STEP, rounding=ROUND_HALF_UP),
                due_on=due_on,
                days=days,
                due_date=due_date,
            )
        )
    return milestones


def _reached_tower(entry: dict) -> str | None:
    tower = entry.get("tower_id")
    return str(tower) if tower else None


def reached_on_for(reached: list | None, key: str, tower_id: UUID | None) -> date | None:
    """When an event milestone was marked reached for this unit — for the whole project or for its tower (the
    earliest mark that covers it). None = not reached yet."""
    tower = str(tower_id) if tower_id else None
    dates: list[date] = []
    for entry in reached or []:
        if not isinstance(entry, dict) or entry.get("key") != key:
            continue
        scope = _reached_tower(entry)
        if scope is not None and scope != tower:
            continue
        try:
            dates.append(date.fromisoformat(str(entry.get("reached_on"))[:10]))
        except ValueError:
            continue
    return min(dates) if dates else None


def _new_row(booking_id: UUID, milestone: Milestone, due: date, base: Decimal, today: date) -> PaymentSchedule:
    demand = demand_for(milestone.percent, base)
    return PaymentSchedule(
        booking_id=booking_id,
        installment_name=milestone.label,
        due_date=due,
        demand_amount=demand,
        paid_amount=_ZERO,
        outstanding=demand,
        is_overdue=(demand > 0 and due < today),
        milestone_key=milestone.key,
        percent=milestone.percent,
    )


async def apply_payment_plan(
    session: AsyncSession, booking: Booking, unit: Unit, project: Project | None, on: date
) -> list[PaymentSchedule]:
    """Give a booking its project's payment plan (no-op when the project has none — the caller keeps the legacy
    demand_schedule path). `on` is the booking's date. Rows for milestones the booking already has are left
    alone, so calling this twice never doubles a demand."""
    plan = project.payment_plan if project is not None else None
    if not plan:
        return []
    booking.payment_plan = copy.deepcopy(plan)
    if booking.id is None:
        await session.flush()  # the demands need the booking's id
    have = set(
        (
            await session.scalars(
                select(PaymentSchedule.milestone_key).where(
                    PaymentSchedule.booking_id == booking.id, PaymentSchedule.milestone_key.is_not(None)
                )
            )
        ).all()
    )
    base = plan_base(booking, unit)
    today = date.today()
    rows: list[PaymentSchedule] = []
    for milestone in parse_plan(plan):
        if milestone.key in have:
            continue
        if milestone.due_on == "on_booking":
            due = on
        elif milestone.due_on == "days_after_booking":
            due = on + timedelta(days=milestone.days or 0)
        elif milestone.due_on == "on_date":
            if milestone.due_date is None:
                continue
            due = milestone.due_date
        elif milestone.due_on in EVENT_DUE_ON:
            reached = reached_on_for(project.milestones_reached, milestone.key, unit.tower_id)
            if reached is None:
                continue  # pending: raised when the builder marks it reached
            due = max(on, reached)
        else:
            continue
        row = _new_row(booking.id, milestone, due, base, today)
        session.add(row)
        rows.append(row)
        have.add(milestone.key)
    return rows


async def _rows_with_money(session: AsyncSession, row_ids: list[UUID]) -> set[UUID]:
    """Rows that have a receipt or a live (not deleted) invoice against them — never re-priced or removed."""
    if not row_ids:
        return set()
    invoiced = await session.scalars(
        select(BookingInvoice.schedule_id).where(
            BookingInvoice.schedule_id.in_(row_ids), BookingInvoice.is_deleted.is_(False)
        )
    )
    receipted = await session.scalars(select(PaymentReceipt.schedule_id).where(PaymentReceipt.schedule_id.in_(row_ids)))
    return {i for i in invoiced.all() if i is not None} | {i for i in receipted.all() if i is not None}


async def reprice_plan_rows(session: AsyncSession, booking: Booking, unit: Unit | None = None) -> int:
    """After the booking's price is saved: rows that follow the price (percent set) and have no money against
    them yet (nothing paid, no receipt, no live invoice) are re-worked from the new price. Returns how many."""
    rows = (
        await session.scalars(
            select(PaymentSchedule)
            .where(
                PaymentSchedule.booking_id == booking.id,
                PaymentSchedule.percent.is_not(None),
                PaymentSchedule.paid_amount == 0,
            )
            .order_by(PaymentSchedule.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    if not rows:
        return 0
    with_money = await _rows_with_money(session, [r.id for r in rows])
    base = plan_base(booking, unit)
    today = date.today()
    changed = 0
    for row in rows:
        if row.id in with_money or (row.paid_amount or _ZERO) != 0 or row.percent is None:
            continue
        demand = demand_for(Decimal(row.percent), base)
        row.demand_amount = demand
        row.outstanding = demand
        row.is_overdue = demand > 0 and row.due_date < today
        changed += 1
    return changed


# ---------------------------------------------------------------------------
# Endpoints — mark a milestone reached (project) / raise it on one booking
#
# Locks: project → bookings → demand rows, always in that order. Projects and bookings are locked FOR NO KEY
# UPDATE (key_share): it serialises these money writes but still lets a payment or invoice insert its row that
# references the booking — a plain FOR UPDATE would block that foreign-key check and could deadlock with a payment
# that already holds its demand row. Rows that may change or be deleted are locked FOR UPDATE.
# ---------------------------------------------------------------------------

async def _lock_project(session: AsyncSession, project_id: UUID) -> Project:
    project = (
        await session.execute(
            select(Project)
            .where(Project.id == project_id)
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if project is None or project.is_deleted:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _booking_scope(project_id: UUID, tower_ids: list[UUID] | None, skip_towers: set[UUID] | None = None) -> list:
    """WHERE terms (over Booking joined to Unit): live (not deleted) bookings of the project's units, limited to
    some towers when given."""
    terms = [Unit.project_id == project_id, Booking.is_deleted.is_(False)]
    if tower_ids:
        terms.append(Unit.tower_id.in_(tower_ids))
    if skip_towers:
        terms.append(Unit.tower_id.not_in(skip_towers))
    return terms


async def _project_read(session: AsyncSession, project: Project) -> ProjectRead:
    await session.refresh(project)
    return ProjectRead.model_validate(project)


def _concurrent_raise() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail="This milestone was just raised by someone else — refresh the page to see it.",
    )


@router.post(
    "/inventory/projects/{project_id}/payment-plan/{key}/reached",
    response_model=MilestoneReachedResult,
)
async def mark_milestone_reached(
    project_id: UUID,
    key: str,
    payload: MilestoneReachedCreate,
    _: object = Depends(require_permissions(PermissionCode.FINANCE_RECORD_PAYMENT)),
    session: AsyncSession = Depends(get_db_session),
):
    """Mark a stage / possession / registration milestone reached (whole project, or some towers) and raise its
    demand, due on the reached date, on every live booking there that holds it and hasn't had it yet."""
    # The project lock serialises marks, undos and new bookings (they read the marks under a share lock), so a
    # booking can't slip in between the mark and the raise and miss its demand.
    project = await _lock_project(session, project_id)
    milestone = next((m for m in parse_plan(project.payment_plan) if m.key == key), None)
    if milestone is None:
        raise HTTPException(status_code=404, detail="That milestone isn't in this project's payment plan.")
    if milestone.due_on not in EVENT_DUE_ON:
        raise HTTPException(
            status_code=422,
            detail=f"“{milestone.label}” falls due on booking or on a date, so there is nothing to mark — only "
            "stage, possession and registration milestones are marked reached.",
        )

    tower_ids = list(dict.fromkeys(payload.tower_ids or []))
    if tower_ids:
        found = set(
            (
                await session.scalars(
                    select(Tower.id).where(
                        Tower.id.in_(tower_ids), Tower.project_id == project_id, Tower.is_deleted.is_(False)
                    )
                )
            ).all()
        )
        if found != set(tower_ids):
            raise HTTPException(status_code=422, detail="Pick towers of this project.")

    # Record the mark (replacing an earlier mark of the same scope). A new list, so the JSON column is saved.
    scopes = [str(t) for t in tower_ids] or [None]
    marks = [
        e for e in (project.milestones_reached or [])
        if not (isinstance(e, dict) and e.get("key") == key and _reached_tower(e) in scopes)
    ]
    reached_on = payload.reached_on
    marks += [{"key": key, "tower_id": scope, "reached_on": reached_on.isoformat()} for scope in scopes]
    project.milestones_reached = marks

    # Lock the bookings (in a fixed order) before looking for their rows, so a concurrent per-booking raise is
    # either seen here or sees this one.
    pairs = (
        await session.execute(
            select(Booking, Unit)
            .join(Unit, Booking.unit_id == Unit.id)
            .where(*_booking_scope(project_id, tower_ids), Booking.status != BookingStatus.cancelled)
            .order_by(Booking.id)
            .with_for_update(of=Booking, key_share=True)
            .execution_options(populate_existing=True)
        )
    ).all()
    holders = [
        (booking, unit, m)
        for booking, unit in pairs
        for m in parse_plan(booking.payment_plan)
        if m.key == key
    ]
    already = set(
        (
            await session.scalars(
                select(PaymentSchedule.booking_id)
                .join(Booking, PaymentSchedule.booking_id == Booking.id)
                .join(Unit, Booking.unit_id == Unit.id)
                .where(Unit.project_id == project_id, PaymentSchedule.milestone_key == key)
            )
        ).all()
    )
    today = date.today()
    raised, already_raised, amount = 0, 0, _ZERO
    for booking, unit, booking_milestone in holders:
        if booking.id in already:
            already_raised += 1
            continue
        # The booking's own copy of the plan sets the % (the buyer's terms), not today's project plan.
        row = _new_row(booking.id, booking_milestone, reached_on, plan_base(booking, unit), today)
        session.add(row)
        raised += 1
        amount += row.demand_amount
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise _concurrent_raise() from None
    return MilestoneReachedResult(
        raised=raised,
        already_raised=already_raised,
        amount=amount,
        project=await _project_read(session, project),
    )


@router.delete(
    "/inventory/projects/{project_id}/payment-plan/{key}/reached",
    response_model=MilestoneUndoResult,
)
async def undo_milestone_reached(
    project_id: UUID,
    key: str,
    tower_id: UUID | None = Query(default=None),
    _: object = Depends(require_permissions(PermissionCode.FINANCE_RECORD_PAYMENT)),
    session: AsyncSession = Depends(get_db_session),
):
    """Take back a "reached" mark (tower_id absent = the whole-project mark) and remove the demands it raised that
    have nothing against them yet. Paid / receipted / invoiced demands stay and are counted as kept."""
    project = await _lock_project(session, project_id)
    scope = str(tower_id) if tower_id else None
    marks = [e for e in (project.milestones_reached or []) if isinstance(e, dict)]
    undone = [e for e in marks if e.get("key") == key and _reached_tower(e) == scope]
    if not undone:
        raise HTTPException(
            status_code=404,
            detail="This milestone isn't marked reached for that tower." if scope
            else "This milestone isn't marked reached for the whole project.",
        )
    remaining = [e for e in marks if e not in undone]
    project.milestones_reached = remaining or None

    # Bookings still covered by another mark of this milestone keep their demand: a whole-project undo skips
    # towers that have their own mark, and a tower undo removes nothing while the whole-project mark stands.
    still_whole = any(e.get("key") == key and _reached_tower(e) is None for e in remaining)
    removed = kept = 0
    if not (scope is not None and still_whole):
        skip_towers: set[UUID] = set()
        if scope is None:
            for e in remaining:
                if e.get("key") == key and _reached_tower(e):
                    try:
                        skip_towers.add(UUID(_reached_tower(e)))
                    except ValueError:
                        continue
        scope_terms = _booking_scope(project_id, [tower_id] if tower_id else None, skip_towers)
        # Lock the bookings first (same order as a mark), then their rows of this milestone.
        await session.execute(
            select(Booking.id)
            .join(Unit, Booking.unit_id == Unit.id)
            .where(*scope_terms)
            .order_by(Booking.id)
            .with_for_update(of=Booking, key_share=True)
        )
        rows = (
            await session.scalars(
                select(PaymentSchedule)
                .join(Booking, PaymentSchedule.booking_id == Booking.id)
                .join(Unit, Booking.unit_id == Unit.id)
                .where(*scope_terms, PaymentSchedule.milestone_key == key)
                .order_by(PaymentSchedule.id)
                .with_for_update(of=PaymentSchedule)
                .execution_options(populate_existing=True)
            )
        ).all()
        with_money = await _rows_with_money(session, [r.id for r in rows])
        for row in rows:
            if (row.paid_amount or _ZERO) != 0 or row.id in with_money:
                kept += 1
                continue
            await session.delete(row)
            removed += 1
    await session.commit()
    return MilestoneUndoResult(removed=removed, kept=kept, project=await _project_read(session, project))


@router.post("/bookings/{booking_id}/payment-plan/{key}/raise", response_model=BookingRead)
async def raise_booking_milestone(
    booking_id: UUID,
    key: str,
    payload: MilestoneRaise,
    _: object = Depends(require_permissions(PermissionCode.FINANCE_RECORD_PAYMENT)),
    session: AsyncSession = Depends(get_db_session),
):
    """Raise one milestone of the booking's plan now (e.g. its registration, or a dated row that was deleted),
    due on the given date — a % of the booking's price like the rest of its plan."""
    # Local import: router.py imports this module.
    from app.real_estate.router import _booking_read

    booking = (
        await session.execute(
            select(Booking)
            .where(Booking.id == booking_id)
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if booking is None or booking.is_deleted:
        raise HTTPException(status_code=404, detail="Booking not found")
    milestone = next((m for m in parse_plan(booking.payment_plan) if m.key == key), None)
    if milestone is None:
        raise HTTPException(status_code=404, detail="That milestone isn't in this booking's payment plan.")
    if booking.status == BookingStatus.cancelled:
        raise HTTPException(status_code=409, detail="This booking is cancelled — nothing more can be demanded on it.")
    existing = await session.scalar(
        select(PaymentSchedule.id).where(
            PaymentSchedule.booking_id == booking.id, PaymentSchedule.milestone_key == key
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"“{milestone.label}” is already raised on this booking.")
    unit = await session.get(Unit, booking.unit_id)
    session.add(_new_row(booking.id, milestone, payload.due_date, plan_base(booking, unit), date.today()))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise _concurrent_raise() from None
    return await _booking_read(session, booking_id)
