"""Real estate API routes — inventory, site visits, bookings."""
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_permissions
from app.core import storage
from app.core.exceptions import NotFoundError
from app.core.pdf import html_to_pdf
from app.core.permissions import ASSIGNED_ONLY_LEAD_ROLES, PermissionCode
from app.database.enums import BookingStatus, InvoiceStatus, UnitStatus, UnitType
from app.database.session import get_db_session
from app.models.customer import Customer
from app.models.lead import Lead
from app.models.user import User
from app.real_estate.documents import (
    render_booking_document,
    render_installment_invoice,
    render_payment_receipt,
    render_token_receipt,
)
from app.real_estate.inventory_layout import (
    MAX_NEW_UNITS_PER_SAVE,
    PARKING_BLOCK_NAME,
    ExistingUnit,
    NewUnit,
    is_parking_block,
    number_units,
    plan_parking,
    plan_tower_units,
)
from app.real_estate.models import (
    Booking,
    BookingInvoice,
    BookingKycDoc,
    BookingRefund,
    PaymentReceipt,
    PaymentSchedule,
    Project,
    ProjectMedia,
    SiteVisit,
    Tower,
    Unit,
)
from app.services.customer_lifecycle import recompute_ltv
from app.services.email import EmailService
from app.services.notifications import NotificationService
from app.real_estate.schemas import (
    BookingCancel,
    BookingCreate,
    BookingKycDocRead,
    BookingRead,
    BookingRefundCreate,
    BookingInvoiceCreate,
    BookingInvoiceRead,
    BookingInvoiceStatusUpdate,
    BookingRegister,
    BookingStepAdvance,
    BookingTokenUpdate,
    CollectionLedgerEntry,
    PaymentPlanCreate,
    PaymentReceiptCreate,
    PaymentScheduleCreate,
    PaymentScheduleRead,
    PaymentScheduleUpdate,
    PossessionChecklistUpdate,
    PricingUpdate,
    ProjectCreate,
    ProjectFullCreate,
    ProjectInventorySync,
    ProjectInventorySyncResult,
    ProjectMediaRead,
    ProjectPossessionRollup,
    ProjectPossessionSummary,
    ProjectPossessionUnit,
    ProjectRead,
    ProjectTowerCreate,
    ProjectUpdate,
    ProjectWithTowersRead,
    SiteVisitCreate,
    SiteVisitRead,
    SiteVisitUpdate,
    TowerCreate,
    TowerRead,
    TowerUpdate,
    UnitBatchCreate,
    UnitRead,
    UnitStatusUpdate,
    UnitUpdate,
)
from app.services.realtime import realtime_manager

router = APIRouter()


async def _booking_owner_id(session: AsyncSession, booking: Booking) -> UUID | None:
    """Who 'owns' a booking for notification purposes: the customer's owner, else
    the source lead's assignee, else whoever created the booking."""
    if booking.customer_id:
        cust = await session.get(Customer, booking.customer_id)
        if cust and cust.current_owner_id:
            return cust.current_owner_id
    if booking.lead_id:
        lead = await session.get(Lead, booking.lead_id)
        if lead and lead.assigned_to_id:
            return lead.assigned_to_id
    return getattr(booking, "created_by_id", None)


async def _notify(session: AsyncSession, user_id: UUID | None, message: str) -> None:
    """Best-effort in-app notification (no-op when there's no recipient)."""
    if user_id:
        await NotificationService(session).create_notification(user_id=user_id, message=message)


_email_service = EmailService()


def _fmt_inr(value) -> str:
    try:
        return "₹{:,.0f}".format(Decimal(str(value)))
    except (InvalidOperation, TypeError, ValueError):
        return str(value)


def _unit_label(booking) -> str:
    """Human unit label from an eager-loaded booking (unit.tower.project)."""
    unit = booking.unit
    if unit is None:
        return "your unit"
    parts = [unit.project_name, unit.tower_name, unit.unit_number]
    return " · ".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Inventory — projects
# ---------------------------------------------------------------------------

@router.get("/inventory/projects", response_model=list[ProjectWithTowersRead])
async def list_projects(
    _: object = Depends(require_permissions(PermissionCode.LEAD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    stmt = (
        select(Project)
        .where(Project.is_deleted.is_(False))
        .options(
            selectinload(Project.towers.and_(Tower.is_deleted.is_(False)))
            .selectinload(Tower.units.and_(Unit.is_deleted.is_(False))),
            selectinload(Project.media),
        )
        .order_by(Project.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


def _json_demand_schedule(value):
    """Serialise a demand-schedule list (Decimal percent / date due_date) into JSON-safe
    dicts for the Project.demand_schedule JSON column."""
    if not value:
        return value
    out = []
    for m in value:
        due = m.get("due_date")
        out.append(
            {
                "label": m.get("label"),
                "percent": float(m.get("percent") or 0),
                "due_date": due.isoformat() if hasattr(due, "isoformat") else (str(due) if due else None),
            }
        )
    return out


@router.post("/inventory/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    _: object = Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    data = payload.model_dump()
    data["demand_schedule"] = _json_demand_schedule(data.get("demand_schedule"))
    project = Project(**data)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


# Static path before /{project_id} so "full" isn't parsed as an id.
@router.post("/inventory/projects/full", response_model=ProjectWithTowersRead, status_code=status.HTTP_201_CREATED)
async def create_project_full(
    payload: ProjectFullCreate,
    _: object = Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    """Create a project + its towers + each tower's units + its parking atomically (the one-page project
    form). All-or-nothing: a failure rolls the whole thing back."""
    # Everything except the nested towers/parking maps 1:1 onto Project columns (incl. the
    # Phase-B detail + default box-price fields).
    data = payload.model_dump(exclude={"towers", "parking"})
    data["demand_schedule"] = _json_demand_schedule(data.get("demand_schedule"))
    _check_tower_names([t.name for t in payload.towers])
    tower_plans = [(t, plan_tower_units(t.name.strip(), _tower_specs(t), [])) for t in payload.towers]
    planned_numbers = {n.unit_number for _, plan in tower_plans for n in plan.new}
    parking_plan = plan_parking(payload.parking, [], planned_numbers)
    _check_new_unit_cap(sum(len(plan.new) for _, plan in tower_plans) + len(parking_plan.new))

    project = Project(**data)
    session.add(project)
    await session.flush()
    for tspec, plan in tower_plans:
        tower = Tower(project_id=project.id, name=tspec.name.strip(), total_floors=tspec.total_floors)
        session.add(tower)
        await session.flush()
        _add_units(session, project.id, tower.id, plan.new)
    if parking_plan.new:
        block = Tower(project_id=project.id, name=PARKING_BLOCK_NAME, total_floors=1)
        session.add(block)
        await session.flush()
        _add_parking(session, project, block.id, parking_plan.new)
    _apply_built_totals(
        project,
        [t.total_floors for t in payload.towers],
        len(parking_plan.new)
        + sum(1 for _, plan in tower_plans for n in plan.new if n.spec.unit_type == UnitType.parking),
    )
    await session.commit()
    return await _load_project_with_inventory(session, project.id)


@router.post("/inventory/projects/{project_id}/inventory", response_model=ProjectInventorySyncResult)
async def sync_project_inventory(
    project_id: UUID,
    payload: ProjectInventorySync,
    _: object = Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    """Edit project → Save: add the towers, units and parking the page describes that don't exist yet.

    Additive and idempotent (see inventory_layout): saving the same page twice creates nothing the second time,
    and existing units — with any booking on them — are never changed or removed. Tower cards are matched by
    `tower_id`, else by name, so a double-click or a stale tab can't create a second copy of a tower."""
    # Lock the project row: two Saves at once (double-click, two tabs) would both see the same gap and fill it.
    project = (
        await session.execute(select(Project).where(Project.id == project_id).with_for_update())
    ).scalar_one_or_none()
    if not project or project.is_deleted:
        raise HTTPException(status_code=404, detail="Project not found")

    towers = list(
        (
            await session.execute(
                select(Tower)
                .where(Tower.project_id == project_id, Tower.is_deleted.is_(False))
                .order_by(Tower.created_at, Tower.name)
            )
        ).scalars()
    )
    # Every unit of the project, archived ones included (they count toward the layout and keep their numbers).
    units = (
        await session.execute(
            select(Unit.tower_id, Unit.unit_number, Unit.unit_type, Unit.floor, Unit.is_deleted).where(
                Unit.project_id == project_id
            )
        )
    ).all()
    by_id = {t.id: t for t in towers}
    live_tower_ids = set(by_id)

    _check_tower_names([card.name for card in payload.towers])
    claimed: set[UUID] = set()
    for card in payload.towers:
        if card.tower_id is None:
            continue
        tower = by_id.get(card.tower_id)
        if tower is None or is_parking_block(tower.name):
            raise HTTPException(
                status_code=404,
                detail="A tower on this page no longer exists (it may have been archived). Reload the page and try again.",
            )
        if card.tower_id in claimed:
            raise HTTPException(status_code=422, detail=f"The tower “{tower.name}” appears twice on this page.")
        claimed.add(card.tower_id)
    unclaimed_by_name = {
        t.name.strip().casefold(): t for t in towers if t.id not in claimed and not is_parking_block(t.name)
    }

    def existing_in(tower_id: UUID) -> list[ExistingUnit]:
        return [
            ExistingUnit(unit_number=u.unit_number, unit_type=u.unit_type, floor=u.floor, archived=u.is_deleted)
            for u in units
            if u.tower_id == tower_id
        ]

    plans = []
    for card in payload.towers:
        name = card.name.strip()
        tower = by_id[card.tower_id] if card.tower_id else unclaimed_by_name.pop(name.casefold(), None)
        plans.append((card, tower, plan_tower_units(name, _tower_specs(card), existing_in(tower.id) if tower else [])))

    project_numbers = {u.unit_number for u in units} | {n.unit_number for _, _, plan in plans for n in plan.new}
    parking_plan = plan_parking(
        payload.parking,
        [
            ExistingUnit(unit_number=u.unit_number, unit_type=u.unit_type, floor=u.floor, archived=u.is_deleted)
            for u in units
            if u.unit_type == UnitType.parking.value and u.tower_id in live_tower_ids
        ],
        project_numbers,
    )
    new_tower_units = sum(len(plan.new) for _, _, plan in plans)
    _check_new_unit_cap(new_tower_units + len(parking_plan.new))

    notes: list[str] = []
    created_towers = 0
    for card, tower, plan in plans:
        name = card.name.strip()
        if tower is None:
            tower = Tower(project_id=project.id, name=name, total_floors=card.total_floors)
            session.add(tower)
            await session.flush()
            towers.append(tower)
            created_towers += 1
        else:
            top_floor = max((u.floor for u in units if u.tower_id == tower.id and not u.is_deleted), default=0)
            if card.total_floors < top_floor:
                notes.append(f"{name}: kept {top_floor} floors — it has units up to floor {top_floor}.")
            tower.name = name
            tower.total_floors = max(card.total_floors, top_floor)
        notes.extend(plan.notes)
        _add_units(session, project.id, tower.id, plan.new)

    notes.extend(parking_plan.notes)
    if parking_plan.new:
        block = next((t for t in towers if is_parking_block(t.name)), None)
        if block is None:
            block = Tower(project_id=project.id, name=PARKING_BLOCK_NAME, total_floors=1)
            session.add(block)
            await session.flush()
            towers.append(block)
        _add_parking(session, project, block.id, parking_plan.new)

    parking_spots = (
        sum(
            1
            for u in units
            if u.unit_type == UnitType.parking.value and not u.is_deleted and u.tower_id in live_tower_ids
        )
        + sum(1 for _, _, plan in plans for n in plan.new if n.spec.unit_type == UnitType.parking)
        + len(parking_plan.new)
    )
    _apply_built_totals(project, [t.total_floors for t in towers if not is_parking_block(t.name)], parking_spots)
    await session.commit()

    return {
        "project": ProjectWithTowersRead.model_validate(await _load_project_with_inventory(session, project.id)),
        "created": {"towers": created_towers, "units": new_tower_units, "parking": len(parking_plan.new)},
        "notes": notes,
    }


def _tower_specs(card: ProjectTowerCreate) -> list[UnitBatchCreate]:
    # A tower can carry several unit-type batches (residential + shop + godown …); `units` is the legacy single one.
    return list(card.unit_specs) + ([card.units] if card.units is not None else [])


def _check_tower_names(names: list[str]) -> None:
    seen: set[str] = set()
    for raw in names:
        name = raw.strip()
        if not name:
            raise HTTPException(status_code=422, detail="Every tower needs a name.")
        if is_parking_block(name):
            raise HTTPException(
                status_code=422,
                detail=f"“{PARKING_BLOCK_NAME}” is kept for the project's parking — give this tower another name.",
            )
        if name.casefold() in seen:
            raise HTTPException(status_code=422, detail=f"Two towers are named “{name}” — give each tower its own name.")
        seen.add(name.casefold())


def _check_new_unit_cap(count: int) -> None:
    if count > MAX_NEW_UNITS_PER_SAVE:
        raise HTTPException(
            status_code=422,
            detail=(
                f"This would create {count:,} units — more than {MAX_NEW_UNITS_PER_SAVE:,} in one save. "
                "Check the floors, flats per floor and parking counts."
            ),
        )


def _add_units(session: AsyncSession, project_id: UUID, tower_id: UUID, new_units: list[NewUnit]) -> None:
    for new in new_units:
        spec = new.spec
        session.add(
            Unit(
                project_id=project_id,
                tower_id=tower_id,
                floor=new.floor,
                unit_number=new.unit_number,
                unit_type=spec.unit_type.value,
                area=spec.area,
                carpet_area=spec.carpet_area,
                built_up_area=spec.built_up_area,
                base_price=spec.base_price,
                area_unit=spec.area_unit,
                facing=spec.facing,
                status=UnitStatus.available,
            )
        )


def _add_parking(session: AsyncSession, project: Project, block_id: UUID, spots: list[tuple[str, str]]) -> None:
    # A spot has no area; its price is the project's parking cost (editable per spot later).
    for _parking_type, number in spots:
        session.add(
            Unit(
                project_id=project.id,
                tower_id=block_id,
                floor=0,
                unit_number=number,
                unit_type=UnitType.parking.value,
                area=Decimal("0"),
                base_price=project.parking_cost or Decimal("0"),
                area_unit="sqft",
                status=UnitStatus.available,
            )
        )


def _apply_built_totals(project: Project, tower_floors: list[int], parking_spots: int) -> None:
    """Keep the project's headline numbers in step with the inventory that exists. A number is only overwritten
    once something of that kind is built — a project whose inventory isn't set up yet keeps what it was given."""
    if tower_floors:
        project.total_towers = len(tower_floors)
        project.total_floors = max(tower_floors)
    if parking_spots:
        project.total_garages = parking_spots


async def _load_project_with_inventory(session: AsyncSession, project_id: UUID) -> Project:
    stmt = (
        select(Project)
        .where(Project.id == project_id, Project.is_deleted.is_(False))
        .options(
            selectinload(Project.towers.and_(Tower.is_deleted.is_(False)))
            .selectinload(Tower.units.and_(Unit.is_deleted.is_(False))),
            selectinload(Project.media),
        )
        .execution_options(populate_existing=True)
    )
    return (await session.execute(stmt)).scalar_one()


@router.get("/inventory/projects/{project_id}", response_model=ProjectWithTowersRead)
async def get_project(
    project_id: UUID,
    _: object = Depends(require_permissions(PermissionCode.LEAD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    stmt = (
        select(Project)
        .where(Project.id == project_id, Project.is_deleted.is_(False))
        .options(
            selectinload(Project.towers.and_(Tower.is_deleted.is_(False)))
            .selectinload(Tower.units.and_(Unit.is_deleted.is_(False))),
            selectinload(Project.media),
        )
    )
    project = (await session.execute(stmt)).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/inventory/projects/{project_id}/possession", response_model=ProjectPossessionRollup)
async def get_project_possession(
    project_id: UUID,
    _: object = Depends(require_permissions(PermissionCode.LEAD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    """Project-wise possession & registration rollup (Phase C3): every unit + its
    confirmed booking's registration/possession status + summary counts."""
    project = await session.get(Project, project_id)
    if not project or project.is_deleted:
        raise HTTPException(status_code=404, detail="Project not found")

    units = (
        await session.execute(
            select(Unit)
            .where(Unit.project_id == project_id, Unit.is_deleted.is_(False))
            .options(selectinload(Unit.tower))
            .order_by(Unit.floor, Unit.unit_number)
        )
    ).scalars().all()

    # At most one CONFIRMED booking per unit (partial unique index), so unit→booking is 1:1.
    by_unit: dict[UUID, Booking] = {}
    unit_ids = [u.id for u in units]
    if unit_ids:
        bookings = (
            await session.execute(
                select(Booking)
                .where(
                    Booking.unit_id.in_(unit_ids),
                    Booking.is_deleted.is_(False),
                    Booking.status == BookingStatus.confirmed,
                )
                .options(selectinload(Booking.customer))
            )
        ).scalars().all()
        by_unit = {b.unit_id: b for b in bookings}

    rows: list[ProjectPossessionUnit] = []
    booked = registered = possession_complete = 0
    for u in units:
        b = by_unit.get(u.id)
        checklist = (b.possession_checklist if b else None) or []
        done = sum(1 for x in checklist if x)
        total = len(checklist)
        is_registered = u.status in (UnitStatus.registered, UnitStatus.sold) or bool(b and b.registration_number)
        if b is not None:
            booked += 1
        if is_registered:
            registered += 1
        if total > 0 and done == total:
            possession_complete += 1
        rows.append(
            ProjectPossessionUnit(
                unit_id=u.id,
                unit_number=u.unit_number,
                tower_name=u.tower.name if u.tower else None,
                floor=u.floor,
                unit_status=u.status,
                booking_id=b.id if b else None,
                customer_name=(b.customer.contact_name if b and b.customer else None),
                registration_number=(b.registration_number if b else None),
                registered=is_registered,
                possession_done=done,
                possession_total=total,
            )
        )
    return ProjectPossessionRollup(
        project_id=project.id,
        project_name=project.name,
        summary=ProjectPossessionSummary(
            total_units=len(units),
            booked=booked,
            registered=registered,
            possession_complete=possession_complete,
        ),
        units=rows,
    )


# ---------------------------------------------------------------------------
# Inventory — project media (brochures / floor plans / images)
# ---------------------------------------------------------------------------

@router.post(
    "/inventory/projects/{project_id}/media",
    response_model=ProjectMediaRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_project_media(
    project_id: UUID,
    file: UploadFile = File(...),
    media_type: str = Form(...),
    label: str | None = Form(default=None),
    current_user=Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    data = await file.read()
    # Create the row first (flush → id), then upload under a key derived from
    # that id, then persist the key. If the upload 503s (storage unconfigured),
    # the uncommitted row rolls back with the request — no orphan.
    media = ProjectMedia(project_id=project_id, media_type=media_type, file_path="", label=label)
    session.add(media)
    await session.flush()
    key = storage.put_object(
        storage.media_key(current_user.organization_id, project_id, media.id, file.filename or "file"),
        data,
        file.content_type,
    )
    media.file_path = key
    await session.commit()
    await session.refresh(media)
    return media


@router.delete("/inventory/projects/media/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_media(
    media_id: UUID,
    _: object = Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    media = await session.get(ProjectMedia, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    key = media.file_path
    await session.delete(media)
    await session.commit()
    if key:
        try:
            storage.delete_object(key)
        except Exception:  # noqa: BLE001 — row is already gone; object cleanup is best-effort
            pass


# ---------------------------------------------------------------------------
# Inventory — towers + units (creation)
# ---------------------------------------------------------------------------

@router.post(
    "/inventory/projects/{project_id}/towers",
    response_model=TowerRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_tower(
    project_id: UUID,
    payload: TowerCreate,
    _: object = Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    project = await session.get(Project, project_id)
    if not project or project.is_deleted:
        raise HTTPException(status_code=404, detail="Project not found")
    tower = Tower(project_id=project_id, name=payload.name, total_floors=payload.total_floors)
    session.add(tower)
    await session.commit()
    # Re-load with its (empty) units so TowerRead serializes without a lazy load.
    stmt = select(Tower).where(Tower.id == tower.id).options(selectinload(Tower.units))
    return (await session.execute(stmt)).scalar_one()


@router.post(
    "/inventory/towers/{tower_id}/units/batch",
    response_model=list[UnitRead],
    status_code=status.HTTP_201_CREATED,
)
async def create_units_batch(
    tower_id: UUID,
    payload: UnitBatchCreate,
    _: object = Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    # Locked so two batches at once can't hand out the same numbers.
    tower = (await session.execute(select(Tower).where(Tower.id == tower_id).with_for_update())).scalar_one_or_none()
    if not tower or tower.is_deleted:
        raise HTTPException(status_code=404, detail="Tower not found")
    project = await session.get(Project, tower.project_id)
    if not project or project.is_deleted:
        raise HTTPException(status_code=404, detail="Project not found")

    # Always adds: numbered after every unit the tower already has (archived included), never a duplicate.
    used = set((await session.execute(select(Unit.unit_number).where(Unit.tower_id == tower_id))).scalars())
    new_units = number_units(payload, used)
    _check_new_unit_cap(len(new_units))
    _add_units(session, tower.project_id, tower.id, new_units)
    await session.commit()
    # Return the tower's units freshly loaded (avoids per-object refresh after commit).
    stmt = (
        select(Unit)
        .where(Unit.tower_id == tower_id, Unit.is_deleted.is_(False))
        .order_by(Unit.floor.desc(), Unit.unit_number)
    )
    return list((await session.execute(stmt)).scalars().all())


@router.get("/inventory/units/{unit_id}", response_model=UnitRead)
async def get_unit(
    unit_id: UUID,
    _: object = Depends(require_permissions(PermissionCode.LEAD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    unit = await session.get(Unit, unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found")
    return unit


@router.patch("/inventory/units/{unit_id}/status", response_model=UnitRead)
async def update_unit_status(
    unit_id: UUID,
    payload: UnitStatusUpdate,
    _: object = Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    unit = await session.get(Unit, unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found")
    unit.status = payload.status
    await session.commit()
    await session.refresh(unit)
    await realtime_manager.broadcast({
        "event": "unit.status_changed",
        "unit_id": str(unit_id),
        "status": payload.status.value,
        "project_id": str(unit.project_id),
    })
    return unit


# ---------------------------------------------------------------------------
# Inventory — edit + archive (soft delete)
# ---------------------------------------------------------------------------

# A unit is safe to archive only before it carries any commitment.
_ARCHIVABLE_UNIT_STATUSES = (UnitStatus.available, UnitStatus.hold)


def _stamp_archived(obj, user_id: UUID | None, when: datetime) -> None:
    obj.is_deleted = True
    obj.deleted_at = when
    obj.deleted_by_id = user_id


@router.patch("/inventory/projects/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    _: object = Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    project = await session.get(Project, project_id)
    if not project or project.is_deleted:
        raise HTTPException(status_code=404, detail="Project not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "demand_schedule":
            value = _json_demand_schedule(value)
        setattr(project, field, value)
    await session.commit()
    await session.refresh(project)
    return project


@router.delete("/inventory/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_project(
    project_id: UUID,
    current_user=Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    project = await session.get(Project, project_id)
    if not project or project.is_deleted:
        raise HTTPException(status_code=404, detail="Project not found")
    in_use = await session.scalar(
        select(func.count())
        .select_from(Unit)
        .where(
            Unit.project_id == project_id,
            Unit.is_deleted.is_(False),
            Unit.status.not_in(_ARCHIVABLE_UNIT_STATUSES),
        )
    )
    if in_use:
        raise HTTPException(status_code=409, detail="Project has booked/registered/sold units; cannot archive.")
    now = datetime.now(UTC)
    values = {"is_deleted": True, "deleted_at": now, "deleted_by_id": current_user.id}
    await session.execute(
        update(Unit).where(Unit.project_id == project_id, Unit.is_deleted.is_(False)).values(**values)
    )
    await session.execute(
        update(Tower).where(Tower.project_id == project_id, Tower.is_deleted.is_(False)).values(**values)
    )
    _stamp_archived(project, current_user.id, now)
    await session.commit()


@router.patch("/inventory/towers/{tower_id}", response_model=TowerRead)
async def update_tower(
    tower_id: UUID,
    payload: TowerUpdate,
    _: object = Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    tower = await session.get(Tower, tower_id)
    if not tower or tower.is_deleted:
        raise HTTPException(status_code=404, detail="Tower not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(tower, field, value)
    await session.commit()
    await session.refresh(tower)
    return tower


@router.delete("/inventory/towers/{tower_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_tower(
    tower_id: UUID,
    current_user=Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    tower = await session.get(Tower, tower_id)
    if not tower or tower.is_deleted:
        raise HTTPException(status_code=404, detail="Tower not found")
    in_use = await session.scalar(
        select(func.count())
        .select_from(Unit)
        .where(
            Unit.tower_id == tower_id,
            Unit.is_deleted.is_(False),
            Unit.status.not_in(_ARCHIVABLE_UNIT_STATUSES),
        )
    )
    if in_use:
        raise HTTPException(status_code=409, detail="Tower has booked/registered/sold units; cannot archive.")
    now = datetime.now(UTC)
    values = {"is_deleted": True, "deleted_at": now, "deleted_by_id": current_user.id}
    await session.execute(
        update(Unit).where(Unit.tower_id == tower_id, Unit.is_deleted.is_(False)).values(**values)
    )
    _stamp_archived(tower, current_user.id, now)
    await session.commit()


@router.patch("/inventory/units/{unit_id}", response_model=UnitRead)
async def update_unit(
    unit_id: UUID,
    payload: UnitUpdate,
    _: object = Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    unit = await session.get(Unit, unit_id)
    if not unit or unit.is_deleted:
        raise HTTPException(status_code=404, detail="Unit not found")
    data = payload.model_dump(exclude_unset=True)
    if "unit_type" in data:
        ut = data.pop("unit_type")
        if ut is not None:
            unit.unit_type = ut.value if hasattr(ut, "value") else ut
    for field, value in data.items():
        setattr(unit, field, value)
    await session.commit()
    await session.refresh(unit)
    return unit


@router.delete("/inventory/units/{unit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_unit(
    unit_id: UUID,
    current_user=Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    unit = await session.get(Unit, unit_id)
    if not unit or unit.is_deleted:
        raise HTTPException(status_code=404, detail="Unit not found")
    if unit.status not in _ARCHIVABLE_UNIT_STATUSES:
        raise HTTPException(status_code=409, detail="Cannot archive a booked/registered/sold unit.")
    _stamp_archived(unit, current_user.id, datetime.now(UTC))
    await session.commit()


# ---------------------------------------------------------------------------
# Site visits
# ---------------------------------------------------------------------------

@router.get("/site-visits", response_model=list[SiteVisitRead])
async def list_site_visits(
    project_id: UUID | None = Query(default=None),
    lead_id: UUID | None = Query(default=None),
    current_user=Depends(require_permissions(PermissionCode.LEAD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    stmt = (
        select(SiteVisit)
        .options(selectinload(SiteVisit.project), selectinload(SiteVisit.lead))
        .order_by(SiteVisit.scheduled_at.desc())
    )
    if project_id:
        stmt = stmt.where(SiteVisit.project_id == project_id)
    if lead_id:
        stmt = stmt.where(SiteVisit.lead_id == lead_id)
    # Front-line reps see only visits assigned to them; managers/owner see all.
    if current_user.role in ASSIGNED_ONLY_LEAD_ROLES:
        stmt = stmt.where(SiteVisit.assigned_to_id == current_user.id)
    return list((await session.execute(stmt)).scalars().all())


async def _site_visit_read(session: AsyncSession, visit_id: UUID) -> SiteVisit:
    stmt = (
        select(SiteVisit)
        .where(SiteVisit.id == visit_id)
        .options(selectinload(SiteVisit.project), selectinload(SiteVisit.lead))
    )
    return (await session.execute(stmt)).scalar_one()


@router.post("/site-visits", response_model=SiteVisitRead, status_code=status.HTTP_201_CREATED)
async def create_site_visit(
    payload: SiteVisitCreate,
    current_user=Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    visit = SiteVisit(**payload.model_dump())
    # A front-line rep's own visit defaults to them (else, unassigned, it would be
    # invisible on their own scoped calendar).
    if visit.assigned_to_id is None and current_user.role in ASSIGNED_ONLY_LEAD_ROLES:
        visit.assigned_to_id = current_user.id
    session.add(visit)
    if visit.assigned_to_id:
        project = await session.get(Project, visit.project_id)
        await _notify(
            session, visit.assigned_to_id,
            f"Site visit scheduled at {project.name if project else 'a project'}.",
        )
    await session.commit()
    result = await _site_visit_read(session, visit.id)
    # Email the assigned rep (best-effort).
    if result.assigned_to_id:
        rep = await session.get(User, result.assigned_to_id)
        if rep and rep.email:
            await _email_service.send_site_visit_notification(
                rep.email,
                rep_name=rep.first_name or "there",
                project=result.project.name if result.project else "a project",
                scheduled_at=result.scheduled_at.strftime("%d %b %Y, %H:%M"),
                lead_name=result.lead.contact_name if result.lead else None,
            )
    return result


@router.patch("/site-visits/{visit_id}", response_model=SiteVisitRead)
async def update_site_visit(
    visit_id: UUID,
    payload: SiteVisitUpdate,
    current_user=Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    visit = await session.get(SiteVisit, visit_id)
    if not visit:
        raise HTTPException(status_code=404, detail="Site visit not found")
    # A front-line rep can only touch their own visits — 404 (not 403) so a visit's
    # existence isn't leaked, mirroring the leads access guard.
    if current_user.role in ASSIGNED_ONLY_LEAD_ROLES and visit.assigned_to_id != current_user.id:
        raise HTTPException(status_code=404, detail="Site visit not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(visit, field, value)
    await session.commit()
    return await _site_visit_read(session, visit_id)


# ---------------------------------------------------------------------------
# Bookings — collection-ledger MUST be registered before /{booking_id}
# ---------------------------------------------------------------------------

@router.get("/bookings/collection-ledger", response_model=list[CollectionLedgerEntry])
async def collection_ledger(
    project_id: UUID | None = Query(default=None),
    _: object = Depends(require_permissions(PermissionCode.FINANCE_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    stmt = (
        select(
            PaymentSchedule,
            Booking.status,
            Unit.unit_number,
            Project.id.label("project_id"),
            Project.name.label("project_name"),
            Customer.contact_name.label("customer_name"),
        )
        .join(Booking, PaymentSchedule.booking_id == Booking.id)
        .join(Unit, Booking.unit_id == Unit.id)
        .join(Project, Unit.project_id == Project.id)
        .outerjoin(Customer, Booking.customer_id == Customer.id)
        .where(Booking.is_deleted.is_(False))
        .order_by(PaymentSchedule.due_date)
    )
    if project_id is not None:
        stmt = stmt.where(Project.id == project_id)
    rows = (await session.execute(stmt)).all()
    today = date.today()
    return [
        CollectionLedgerEntry(
            payment_schedule_id=ps.id,
            booking_id=ps.booking_id,
            installment_name=ps.installment_name,
            due_date=ps.due_date,
            demand_amount=ps.demand_amount,
            paid_amount=ps.paid_amount,
            outstanding=ps.outstanding,
            # Overdue is time-dependent — derive at read time rather than trusting
            # the stored column (which is written nowhere and stays False).
            is_overdue=(ps.outstanding > 0 and ps.due_date < today),
            project_id=proj_id,
            project_name=project_name,
            unit_number=unit_number,
            customer_name=customer_name,
            status=b_status,
        )
        for ps, b_status, unit_number, proj_id, project_name, customer_name in rows
    ]


@router.get("/bookings", response_model=list[BookingRead])
async def list_bookings(
    unit_id: UUID | None = Query(default=None),
    customer_id: UUID | None = Query(default=None),
    lead_id: UUID | None = Query(default=None),
    booking_status: str | None = Query(default=None, alias="status"),
    _: object = Depends(require_permissions(PermissionCode.LEAD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    stmt = (
        select(Booking)
        .options(
            selectinload(Booking.customer),
            selectinload(Booking.unit).selectinload(Unit.tower).selectinload(Tower.project),
            selectinload(Booking.kyc_documents),
            selectinload(Booking.payment_schedules),
            selectinload(Booking.payment_receipts),
            selectinload(Booking.refunds),
        )
        .where(Booking.is_deleted.is_(False))
        .order_by(Booking.created_at.desc())
    )
    if unit_id:
        stmt = stmt.where(Booking.unit_id == unit_id)
    if customer_id:
        stmt = stmt.where(Booking.customer_id == customer_id)
    if lead_id:
        stmt = stmt.where(Booking.lead_id == lead_id)
    if booking_status:
        stmt = stmt.where(Booking.status == booking_status)
    return list((await session.execute(stmt)).scalars().all())


@router.post("/bookings", response_model=BookingRead, status_code=status.HTTP_201_CREATED)
async def create_booking(
    payload: BookingCreate,
    _: object = Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    unit = await session.get(Unit, payload.unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found")
    booking = Booking(**payload.model_dump())
    session.add(booking)
    await session.flush()  # need booking.id to attach schedules
    # Auto-apply the project's demand schedule: % of the unit price on the builder's
    # fixed dates. A manual payment plan (create_payment_plan) later overrides this.
    project = await session.get(Project, unit.project_id) if unit.project_id else None
    schedule = getattr(project, "demand_schedule", None) if project else None
    if schedule:
        total = unit.base_price or Decimal("0")
        today = date.today()
        for m in schedule:
            try:
                percent = Decimal(str(m.get("percent") or 0))
                due = date.fromisoformat(str(m.get("due_date")))
            except (InvalidOperation, TypeError, ValueError):
                continue
            demand = (total * percent / Decimal(100)).quantize(Decimal("0.01"))
            session.add(
                PaymentSchedule(
                    booking_id=booking.id,
                    installment_name=str(m.get("label") or "Installment"),
                    due_date=due,
                    demand_amount=demand,
                    paid_amount=Decimal("0"),
                    outstanding=demand,
                    is_overdue=(demand > 0 and due < today),
                )
            )
    await session.commit()
    stmt = (
        select(Booking)
        .where(Booking.id == booking.id)
        .options(selectinload(Booking.customer), selectinload(Booking.unit).selectinload(Unit.tower).selectinload(Tower.project), selectinload(Booking.kyc_documents), selectinload(Booking.payment_schedules), selectinload(Booking.payment_receipts), selectinload(Booking.refunds))
    )
    return (await session.execute(stmt)).scalar_one()


@router.get("/bookings/{booking_id}", response_model=BookingRead)
async def get_booking(
    booking_id: UUID,
    _: object = Depends(require_permissions(PermissionCode.LEAD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    stmt = (
        select(Booking)
        .where(Booking.id == booking_id, Booking.is_deleted.is_(False))
        .options(selectinload(Booking.customer), selectinload(Booking.unit).selectinload(Unit.tower).selectinload(Tower.project), selectinload(Booking.kyc_documents), selectinload(Booking.payment_schedules), selectinload(Booking.payment_receipts), selectinload(Booking.refunds))
    )
    booking = (await session.execute(stmt)).scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking


@router.post("/bookings/{booking_id}/step/{step}", response_model=BookingRead)
async def advance_booking_step(
    booking_id: UUID,
    step: int,
    payload: BookingStepAdvance,
    _: object = Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    booking = await session.get(Booking, booking_id)
    if not booking or booking.is_deleted:
        raise HTTPException(status_code=404, detail="Booking not found")
    if step not in range(1, 5):
        raise HTTPException(status_code=400, detail="Step must be 1-4")
    booking.step = step
    if payload.customer_id is not None:
        booking.customer_id = payload.customer_id
    if payload.pricing_snapshot is not None:
        booking.pricing_snapshot = payload.pricing_snapshot
    if payload.scheduled_date is not None:
        booking.scheduled_date = payload.scheduled_date
    for ps_data in payload.payment_schedules:
        ps = PaymentSchedule(booking_id=booking.id, **ps_data.model_dump())
        ps.outstanding = ps.demand_amount - ps.paid_amount
        session.add(ps)

    # An EXPLICIT confirm (step 4 + confirm flag) finalizes the booking and marks
    # the unit Booked. Saving the registration date for a document preview passes
    # confirm=False and must not confirm/book. Reject confirmation if the unit is
    # no longer available (prevents overselling the same unit twice). Capture ids
    # before commit so the post-commit broadcast doesn't lazy-load an expired obj.
    booked_unit: tuple[str, str] | None = None
    if step == 4 and payload.confirm and booking.status != BookingStatus.confirmed:
        unit = await session.get(Unit, booking.unit_id)
        if unit is None:
            raise HTTPException(status_code=404, detail="Unit not found")
        if unit.status not in (UnitStatus.available, UnitStatus.hold):
            raise HTTPException(
                status_code=409,
                detail=f"Unit is already {unit.status.value}; it cannot be booked again.",
            )
        booking.status = BookingStatus.confirmed
        unit.status = UnitStatus.booked
        booked_unit = (str(unit.id), str(unit.project_id))
        await _notify(
            session, await _booking_owner_id(session, booking),
            f"Booking confirmed — unit {unit.unit_number}.",
        )
        # Roll the confirmed purchase into the customer's lifetime value.
        if booking.customer_id:
            customer = await session.get(Customer, booking.customer_id)
            if customer is not None:
                await recompute_ltv(session, customer)
    try:
        await session.commit()
    except IntegrityError:
        # The partial unique index (uq_bookings_unit_confirmed) rejected a second
        # confirmed booking for this unit — a concurrent double-confirm lost the race.
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Unit was just booked by another transaction; please pick another unit.",
        )
    if booked_unit is not None:
        await realtime_manager.broadcast(
            {
                "event": "unit.status_changed",
                "unit_id": booked_unit[0],
                "status": UnitStatus.booked.value,
                "project_id": booked_unit[1],
            }
        )
    stmt = (
        select(Booking)
        .where(Booking.id == booking_id)
        .options(selectinload(Booking.customer), selectinload(Booking.unit).selectinload(Unit.tower).selectinload(Tower.project), selectinload(Booking.kyc_documents), selectinload(Booking.payment_schedules), selectinload(Booking.payment_receipts), selectinload(Booking.refunds))
    )
    result = (await session.execute(stmt)).scalar_one()
    # Email the customer their booking confirmation (only when a confirm just
    # happened; best-effort, no-op if email/customer-email is missing).
    if booked_unit is not None and result.customer and result.customer.email:
        await _email_service.send_booking_confirmation(
            result.customer.email,
            customer_name=result.customer.contact_name or "there",
            unit_label=_unit_label(result),
            project=result.unit.project_name if result.unit else None,
            amount=_fmt_inr(_booking_total(result)),
            register_on=result.scheduled_date.isoformat() if result.scheduled_date else None,
        )
    return result


@router.put("/bookings/{booking_id}/pricing", response_model=BookingRead)
async def update_booking_pricing(
    booking_id: UUID,
    payload: PricingUpdate,
    _: object = Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    booking = await session.get(Booking, booking_id)
    if not booking or booking.is_deleted:
        raise HTTPException(status_code=404, detail="Booking not found")
    booking.pricing_snapshot = payload.pricing_snapshot
    await session.commit()
    stmt = (
        select(Booking)
        .where(Booking.id == booking_id)
        .options(selectinload(Booking.customer), selectinload(Booking.unit).selectinload(Unit.tower).selectinload(Tower.project), selectinload(Booking.kyc_documents), selectinload(Booking.payment_schedules), selectinload(Booking.payment_receipts), selectinload(Booking.refunds))
    )
    return (await session.execute(stmt)).scalar_one()


@router.put("/bookings/{booking_id}/possession", response_model=BookingRead)
async def update_possession_checklist(
    booking_id: UUID,
    payload: PossessionChecklistUpdate,
    _: object = Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    booking = await session.get(Booking, booking_id)
    if not booking or booking.is_deleted:
        raise HTTPException(status_code=404, detail="Booking not found")
    booking.possession_checklist = payload.checklist
    await session.commit()
    stmt = (
        select(Booking)
        .where(Booking.id == booking_id)
        .options(selectinload(Booking.customer), selectinload(Booking.unit).selectinload(Unit.tower).selectinload(Tower.project), selectinload(Booking.kyc_documents), selectinload(Booking.payment_schedules), selectinload(Booking.payment_receipts), selectinload(Booking.refunds))
    )
    return (await session.execute(stmt)).scalar_one()


@router.put("/bookings/{booking_id}/token", response_model=BookingRead)
async def record_booking_token(
    booking_id: UUID,
    payload: BookingTokenUpdate,
    _: object = Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    """Record (or update) the token / booking amount on a booking (Phase C)."""
    booking = await session.get(Booking, booking_id)
    if not booking or booking.is_deleted:
        raise HTTPException(status_code=404, detail="Booking not found")
    booking.token_amount = payload.token_amount
    booking.token_received_on = payload.token_received_on
    booking.token_mode = payload.token_mode
    booking.token_reference = payload.token_reference
    await session.commit()
    stmt = (
        select(Booking)
        .where(Booking.id == booking_id)
        .options(selectinload(Booking.customer), selectinload(Booking.unit).selectinload(Unit.tower).selectinload(Tower.project), selectinload(Booking.kyc_documents), selectinload(Booking.payment_schedules), selectinload(Booking.payment_receipts), selectinload(Booking.refunds))
    )
    return (await session.execute(stmt)).scalar_one()


@router.get("/bookings/{booking_id}/documents/{doc_type}")
async def get_booking_document_url(
    booking_id: UUID,
    doc_type: str,
    _: object = Depends(require_permissions(PermissionCode.LEAD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    if doc_type not in {"allotment_letter", "booking_form", "receipt"}:
        raise HTTPException(status_code=404, detail="Unknown document type")
    booking = await session.get(Booking, booking_id)
    if not booking or booking.is_deleted:
        raise HTTPException(status_code=404, detail="Booking not found")
    unit = await session.get(Unit, booking.unit_id)
    project = await session.get(Project, unit.project_id) if unit else None
    tower = await session.get(Tower, unit.tower_id) if unit else None
    customer = (
        await session.get(Customer, booking.customer_id) if booking.customer_id else None
    )
    html, title = render_booking_document(doc_type, booking, unit, project, tower, customer)
    return {"html": html, "title": title}


@router.get("/bookings/{booking_id}/documents/{doc_type}/pdf")
async def get_booking_document_pdf(
    booking_id: UUID,
    doc_type: str,
    current_user=Depends(require_permissions(PermissionCode.LEAD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    """Render the document to a real PDF, store it, and return a presigned URL."""
    if doc_type not in {"allotment_letter", "booking_form", "receipt"}:
        raise HTTPException(status_code=404, detail="Unknown document type")
    booking = await session.get(Booking, booking_id)
    if not booking or booking.is_deleted:
        raise HTTPException(status_code=404, detail="Booking not found")
    unit = await session.get(Unit, booking.unit_id)
    project = await session.get(Project, unit.project_id) if unit else None
    tower = await session.get(Tower, unit.tower_id) if unit else None
    customer = (
        await session.get(Customer, booking.customer_id) if booking.customer_id else None
    )
    html, _title = render_booking_document(doc_type, booking, unit, project, tower, customer)
    pdf = html_to_pdf(html)
    key = storage.put_object(
        storage.doc_key(current_user.organization_id, booking_id, doc_type),
        pdf,
        "application/pdf",
    )
    return {"url": storage.presigned_get_url(key)}


@router.post(
    "/bookings/{booking_id}/kyc",
    response_model=BookingKycDocRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_booking_kyc(
    booking_id: UUID,
    file: UploadFile = File(...),
    doc_type: str = Form(...),
    current_user=Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    """Upload a real KYC file to object storage; store its key on the doc row."""
    booking = await session.get(Booking, booking_id)
    if not booking or booking.is_deleted:
        raise HTTPException(status_code=404, detail="Booking not found")
    data = await file.read()
    doc = BookingKycDoc(booking_id=booking_id, doc_type=doc_type)
    session.add(doc)
    await session.flush()  # assign doc.id for the object key
    key = storage.put_object(
        storage.kyc_key(current_user.organization_id, booking_id, doc.id, file.filename or "file"),
        data,
        file.content_type,
    )
    doc.file_path = key
    await session.commit()
    await session.refresh(doc)
    return doc


@router.get("/bookings/{booking_id}/kyc/{doc_id}/download")
async def download_booking_kyc(
    booking_id: UUID,
    doc_id: UUID,
    _: object = Depends(require_permissions(PermissionCode.LEAD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    doc = await session.get(BookingKycDoc, doc_id)
    if not doc or doc.booking_id != booking_id or not doc.file_path:
        raise HTTPException(status_code=404, detail="KYC document not found")
    return {"url": storage.presigned_get_url(doc.file_path)}


# ---------------------------------------------------------------------------
# Bookings — payment plan + collections
# ---------------------------------------------------------------------------

async def _booking_read(session: AsyncSession, booking_id: UUID) -> Booking:
    """Re-fetch a booking with every relationship a BookingRead needs."""
    stmt = (
        select(Booking)
        .where(Booking.id == booking_id)
        .options(
            selectinload(Booking.customer),
            selectinload(Booking.unit).selectinload(Unit.tower).selectinload(Tower.project),
            selectinload(Booking.kyc_documents),
            selectinload(Booking.payment_schedules),
            selectinload(Booking.payment_receipts),
            selectinload(Booking.refunds),
        )
    )
    booking = (await session.execute(stmt)).scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking


def _booking_total(booking: Booking) -> Decimal:
    """Total consideration: the pricing snapshot's total, else the unit base price."""
    snap = booking.pricing_snapshot or {}
    if isinstance(snap, dict) and snap.get("total") is not None:
        try:
            return Decimal(str(snap["total"]))
        except (InvalidOperation, TypeError):
            pass
    return booking.unit.base_price if booking.unit else Decimal("0")


@router.post("/bookings/{booking_id}/payment-plan", response_model=BookingRead)
async def create_payment_plan(
    booking_id: UUID,
    payload: PaymentPlanCreate,
    _: object = Depends(require_permissions(PermissionCode.FINANCE_RECORD_PAYMENT)),
    session: AsyncSession = Depends(get_db_session),
):
    """Create/replace a booking's installment plan. Amounts come from an explicit
    value or a percentage of the total consideration. Blocked once any money has
    been collected (so a plan is never rewritten out from under recorded payments)."""
    stmt = (
        select(Booking)
        .where(Booking.id == booking_id)
        .options(selectinload(Booking.payment_schedules), selectinload(Booking.unit))
    )
    booking = (await session.execute(stmt)).scalar_one_or_none()
    if not booking or booking.is_deleted:
        raise HTTPException(status_code=404, detail="Booking not found")
    if any((ps.paid_amount or Decimal("0")) > 0 for ps in booking.payment_schedules):
        raise HTTPException(status_code=409, detail="Payments already recorded; cannot replace the plan.")

    for ps in list(booking.payment_schedules):
        await session.delete(ps)

    total = _booking_total(booking)
    today = date.today()
    for inst in payload.installments:
        if inst.amount is not None:
            demand = inst.amount
        elif inst.percentage is not None:
            demand = (total * inst.percentage / Decimal(100)).quantize(Decimal("0.01"))
        else:
            demand = Decimal("0")
        session.add(
            PaymentSchedule(
                booking_id=booking_id,
                installment_name=inst.installment_name,
                due_date=inst.due_date,
                demand_amount=demand,
                paid_amount=Decimal("0"),
                outstanding=demand,
                is_overdue=(demand > 0 and inst.due_date < today),
            )
        )
    await session.commit()
    return await _booking_read(session, booking_id)


@router.post(
    "/bookings/{booking_id}/payment-schedules",
    response_model=PaymentScheduleRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_payment_schedule(
    booking_id: UUID,
    payload: PaymentScheduleCreate,
    _: object = Depends(require_permissions(PermissionCode.FINANCE_RECORD_PAYMENT)),
    session: AsyncSession = Depends(get_db_session),
):
    """Add a single demand row to a booking's schedule (e.g. an installment the
    project template didn't cover). Complements create_payment_plan, which
    replaces the whole plan; this adds one row without disturbing recorded
    payments on the others."""
    booking = await session.get(Booking, booking_id)
    if not booking or booking.is_deleted:
        raise HTTPException(status_code=404, detail="Booking not found")
    demand = payload.demand_amount
    ps = PaymentSchedule(
        booking_id=booking_id,
        installment_name=payload.installment_name,
        due_date=payload.due_date,
        demand_amount=demand,
        paid_amount=Decimal("0"),
        outstanding=demand,
        is_overdue=(demand > 0 and payload.due_date < date.today()),
    )
    session.add(ps)
    await session.commit()
    await session.refresh(ps)
    return ps


@router.patch(
    "/bookings/{booking_id}/payment-schedules/{schedule_id}",
    response_model=PaymentScheduleRead,
)
async def update_payment_schedule(
    booking_id: UUID,
    schedule_id: UUID,
    payload: PaymentScheduleUpdate,
    _: object = Depends(require_permissions(PermissionCode.FINANCE_RECORD_PAYMENT)),
    session: AsyncSession = Depends(get_db_session),
):
    """Edit an individual demand row (label / due date / amount) after it was
    generated. Recorded payments are untouched; outstanding + overdue are
    recomputed. A demand can't be lowered below what's already been paid."""
    ps = await session.get(PaymentSchedule, schedule_id)
    if not ps or ps.booking_id != booking_id:
        raise HTTPException(status_code=404, detail="Installment not found")
    data = payload.model_dump(exclude_unset=True)
    if "installment_name" in data:
        ps.installment_name = data["installment_name"]
    if "due_date" in data:
        ps.due_date = data["due_date"]
    if "demand_amount" in data and data["demand_amount"] is not None:
        if data["demand_amount"] < (ps.paid_amount or Decimal("0")):
            raise HTTPException(
                status_code=409,
                detail="Demand can't be less than the amount already paid.",
            )
        ps.demand_amount = data["demand_amount"]
    ps.outstanding = max(Decimal("0"), ps.demand_amount - (ps.paid_amount or Decimal("0")))
    ps.is_overdue = ps.outstanding > 0 and ps.due_date < date.today()
    await session.commit()
    await session.refresh(ps)
    return ps


@router.delete(
    "/bookings/{booking_id}/payment-schedules/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_payment_schedule(
    booking_id: UUID,
    schedule_id: UUID,
    _: object = Depends(require_permissions(PermissionCode.FINANCE_RECORD_PAYMENT)),
    session: AsyncSession = Depends(get_db_session),
):
    """Remove a demand row. Blocked once any payment has been recorded against it
    (delete the receipts first via a refund flow if truly needed)."""
    ps = await session.get(PaymentSchedule, schedule_id)
    if not ps or ps.booking_id != booking_id:
        raise HTTPException(status_code=404, detail="Installment not found")
    if (ps.paid_amount or Decimal("0")) > 0:
        raise HTTPException(
            status_code=409,
            detail="Payments recorded against this demand; cannot delete it.",
        )
    await session.delete(ps)
    await session.commit()


@router.post("/bookings/{booking_id}/payments", response_model=BookingRead)
async def record_payment(
    booking_id: UUID,
    payload: PaymentReceiptCreate,
    _: object = Depends(require_permissions(PermissionCode.FINANCE_RECORD_PAYMENT)),
    session: AsyncSession = Depends(get_db_session),
):
    """Post a collection against a booking (optionally a specific installment)."""
    booking = await session.get(Booking, booking_id)
    if not booking or booking.is_deleted:
        raise HTTPException(status_code=404, detail="Booking not found")

    if payload.schedule_id is not None:
        ps = await session.get(PaymentSchedule, payload.schedule_id)
        if not ps or ps.booking_id != booking_id:
            raise HTTPException(status_code=404, detail="Installment not found")
        ps.paid_amount = (ps.paid_amount or Decimal("0")) + payload.amount
        ps.outstanding = max(Decimal("0"), ps.demand_amount - ps.paid_amount)
        ps.is_overdue = ps.outstanding > 0 and ps.due_date < date.today()

    session.add(
        PaymentReceipt(
            booking_id=booking_id,
            schedule_id=payload.schedule_id,
            amount=payload.amount,
            paid_on=payload.paid_on,
            mode=payload.mode,
            reference=payload.reference,
            notes=payload.notes,
        )
    )
    await _notify(
        session, await _booking_owner_id(session, booking),
        f"Payment of ₹{payload.amount} recorded.",
    )
    await session.commit()
    result = await _booking_read(session, booking_id)
    # Email the customer a receipt (best-effort).
    if result.customer and result.customer.email:
        await _email_service.send_payment_receipt(
            result.customer.email,
            customer_name=result.customer.contact_name or "there",
            amount=_fmt_inr(payload.amount),
            mode=payload.mode,
            paid_on=payload.paid_on.isoformat(),
            unit_label=_unit_label(result),
            reference=payload.reference,
        )
    return result


@router.get("/bookings/{booking_id}/payments/{receipt_id}/receipt/pdf")
async def get_payment_receipt_pdf(
    booking_id: UUID,
    receipt_id: UUID,
    current_user=Depends(require_permissions(PermissionCode.FINANCE_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    """Render a PDF receipt for one payment, store it, and return a presigned URL."""
    receipt = await session.get(PaymentReceipt, receipt_id)
    if not receipt or receipt.booking_id != booking_id:
        raise HTTPException(status_code=404, detail="Receipt not found")
    booking = await session.get(Booking, booking_id)
    unit = await session.get(Unit, booking.unit_id) if booking else None
    project = await session.get(Project, unit.project_id) if unit else None
    tower = await session.get(Tower, unit.tower_id) if unit else None
    customer = (
        await session.get(Customer, booking.customer_id) if booking and booking.customer_id else None
    )
    html, _title = render_payment_receipt(booking, unit, project, tower, customer, receipt)
    pdf = html_to_pdf(html)
    key = storage.put_object(
        storage.receipt_key(current_user.organization_id, booking_id, receipt_id),
        pdf,
        "application/pdf",
    )
    return {"url": storage.presigned_get_url(key)}


@router.get("/bookings/{booking_id}/token-receipt/pdf")
async def get_token_receipt_pdf(
    booking_id: UUID,
    current_user=Depends(require_permissions(PermissionCode.FINANCE_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    """Render a PDF token receipt, store it, and return a presigned URL."""
    booking = await session.get(Booking, booking_id)
    if not booking or booking.is_deleted:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.token_amount is None:
        raise HTTPException(status_code=404, detail="No token recorded for this booking")
    unit = await session.get(Unit, booking.unit_id)
    project = await session.get(Project, unit.project_id) if unit else None
    tower = await session.get(Tower, unit.tower_id) if unit else None
    customer = (
        await session.get(Customer, booking.customer_id) if booking.customer_id else None
    )
    html, _title = render_token_receipt(booking, unit, project, tower, customer)
    pdf = html_to_pdf(html)
    key = storage.put_object(
        storage.token_receipt_key(current_user.organization_id, booking_id),
        pdf,
        "application/pdf",
    )
    return {"url": storage.presigned_get_url(key)}


# ---------------------------------------------------------------------------
# Bookings — per-installment invoices (demand notes)
# ---------------------------------------------------------------------------

@router.get("/bookings/{booking_id}/invoices", response_model=list[BookingInvoiceRead])
async def list_booking_invoices(
    booking_id: UUID,
    _: object = Depends(require_permissions(PermissionCode.FINANCE_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    stmt = (
        select(BookingInvoice)
        .where(BookingInvoice.booking_id == booking_id, BookingInvoice.is_deleted.is_(False))
        .order_by(BookingInvoice.created_at)
    )
    return list((await session.execute(stmt)).scalars().all())


@router.post(
    "/bookings/{booking_id}/invoices",
    response_model=BookingInvoiceRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_booking_invoice(
    booking_id: UUID,
    payload: BookingInvoiceCreate,
    _: object = Depends(require_permissions(PermissionCode.FINANCE_RECORD_PAYMENT)),
    session: AsyncSession = Depends(get_db_session),
):
    """Raise a demand invoice for a booking. Bind to an installment (copies its
    name / amount / due date) or supply them directly for an ad-hoc invoice."""
    # Reuse finance's per-tenant sequence primitive (own table + prefix → its own
    # independent series). Imported locally to avoid any cross-domain import cycle.
    from app.finance.services import _next_sequence

    booking = await session.get(Booking, booking_id)
    if not booking or booking.is_deleted:
        raise HTTPException(status_code=404, detail="Booking not found")

    installment_name = payload.installment_name
    amount = payload.amount
    due_date = payload.due_date
    if payload.schedule_id is not None:
        schedule = await session.get(PaymentSchedule, payload.schedule_id)
        if not schedule or schedule.booking_id != booking_id:
            raise HTTPException(status_code=404, detail="Installment not found for this booking")
        installment_name = installment_name or schedule.installment_name
        amount = amount if amount is not None else schedule.demand_amount
        due_date = due_date or schedule.due_date
    if not installment_name or amount is None:
        raise HTTPException(
            status_code=400,
            detail="installment_name and amount are required (or provide a schedule_id).",
        )

    async def _build() -> BookingInvoice:
        number = await _next_sequence(session, BookingInvoice, "invoice_number", "INV-RE")
        inv = BookingInvoice(
            booking_id=booking_id,
            schedule_id=payload.schedule_id,
            invoice_number=number,
            installment_name=installment_name,
            amount=amount,
            due_date=due_date,
            status=InvoiceStatus.issued,
        )
        session.add(inv)
        return inv

    invoice = await _build()
    try:
        await session.commit()
    except IntegrityError:
        # A concurrent mint grabbed the same invoice_number — re-mint once.
        await session.rollback()
        invoice = await _build()
        await session.commit()
    await session.refresh(invoice)
    return invoice


@router.patch("/bookings/{booking_id}/invoices/{invoice_id}", response_model=BookingInvoiceRead)
async def update_booking_invoice(
    booking_id: UUID,
    invoice_id: UUID,
    payload: BookingInvoiceStatusUpdate,
    _: object = Depends(require_permissions(PermissionCode.FINANCE_RECORD_PAYMENT)),
    session: AsyncSession = Depends(get_db_session),
):
    invoice = await session.get(BookingInvoice, invoice_id)
    if not invoice or invoice.is_deleted or invoice.booking_id != booking_id:
        raise HTTPException(status_code=404, detail="Invoice not found")
    invoice.status = payload.status
    await session.commit()
    await session.refresh(invoice)
    return invoice


@router.get("/bookings/{booking_id}/invoices/{invoice_id}/pdf")
async def get_booking_invoice_pdf(
    booking_id: UUID,
    invoice_id: UUID,
    current_user=Depends(require_permissions(PermissionCode.FINANCE_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    """Render a PDF for one invoice, store it, and return a presigned URL."""
    invoice = await session.get(BookingInvoice, invoice_id)
    if not invoice or invoice.is_deleted or invoice.booking_id != booking_id:
        raise HTTPException(status_code=404, detail="Invoice not found")
    booking = await session.get(Booking, booking_id)
    unit = await session.get(Unit, booking.unit_id) if booking else None
    project = await session.get(Project, unit.project_id) if unit else None
    tower = await session.get(Tower, unit.tower_id) if unit else None
    customer = (
        await session.get(Customer, booking.customer_id) if booking and booking.customer_id else None
    )
    html, _title = render_installment_invoice(booking, unit, project, tower, customer, invoice)
    pdf = html_to_pdf(html)
    key = storage.put_object(
        storage.invoice_key(current_user.organization_id, booking_id, invoice_id),
        pdf,
        "application/pdf",
    )
    return {"url": storage.presigned_get_url(key)}


@router.post("/bookings/{booking_id}/cancel", response_model=BookingRead)
async def cancel_booking(
    booking_id: UUID,
    payload: BookingCancel,
    _: object = Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    """Cancel a booking and free its unit. Blocked once any payment is recorded
    (the money must be refunded / cleared first)."""
    stmt = (
        select(Booking)
        .where(Booking.id == booking_id)
        .options(selectinload(Booking.payment_receipts))
    )
    booking = (await session.execute(stmt)).scalar_one_or_none()
    if not booking or booking.is_deleted:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.status == BookingStatus.cancelled:
        raise HTTPException(status_code=409, detail="Booking is already cancelled.")
    if booking.payment_receipts:
        raise HTTPException(status_code=409, detail="Payments recorded; refund/clear them before cancelling.")

    booking.status = BookingStatus.cancelled
    booking.cancellation_reason = payload.reason

    # Drop this purchase out of the customer's lifetime value.
    if booking.customer_id:
        customer = await session.get(Customer, booking.customer_id)
        if customer is not None:
            await recompute_ltv(session, customer)

    # Free the unit back to Available — but only if it hasn't progressed past a
    # booking (a registered/sold unit is left alone).
    unit = await session.get(Unit, booking.unit_id)
    freed = bool(unit and unit.status in (UnitStatus.booked, UnitStatus.hold))
    if freed:
        unit.status = UnitStatus.available
    await session.commit()
    if freed and unit:
        await realtime_manager.broadcast({
            "event": "unit.status_changed",
            "unit_id": str(unit.id),
            "status": UnitStatus.available.value,
            "project_id": str(unit.project_id),
        })
    return await _booking_read(session, booking_id)


@router.post("/bookings/{booking_id}/refund", response_model=BookingRead)
async def refund_booking(
    booking_id: UUID,
    payload: BookingRefundCreate,
    _: object = Depends(require_permissions(PermissionCode.FINANCE_REFUND)),
    session: AsyncSession = Depends(get_db_session),
):
    """Refund a paid booking and cancel it. This is the counterpart to /cancel:
    an unpaid booking is cancelled directly, a paid one is cancelled *here* by
    recording the refund (net = collected − deduction) and freeing its unit."""
    stmt = (
        select(Booking)
        .where(Booking.id == booking_id)
        .options(selectinload(Booking.payment_receipts))
    )
    booking = (await session.execute(stmt)).scalar_one_or_none()
    if not booking or booking.is_deleted:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.status == BookingStatus.cancelled:
        raise HTTPException(status_code=409, detail="Booking is already cancelled.")

    gross_paid = sum((r.amount for r in booking.payment_receipts), Decimal("0"))
    if gross_paid <= 0:
        raise HTTPException(
            status_code=409,
            detail="No payments recorded on this booking — use cancel instead of refund.",
        )
    if payload.deduction_amount > gross_paid:
        raise HTTPException(
            status_code=422,
            detail=f"Deduction (₹{payload.deduction_amount}) cannot exceed the amount paid (₹{gross_paid}).",
        )
    refund_amount = gross_paid - payload.deduction_amount

    session.add(
        BookingRefund(
            booking_id=booking_id,
            gross_paid=gross_paid,
            deduction_amount=payload.deduction_amount,
            refund_amount=refund_amount,
            mode=payload.mode,
            refunded_on=payload.refunded_on,
            reference=payload.reference,
            reason=payload.reason,
        )
    )
    booking.status = BookingStatus.cancelled
    booking.cancellation_reason = payload.reason

    # Drop this purchase out of the customer's lifetime value.
    if booking.customer_id:
        customer = await session.get(Customer, booking.customer_id)
        if customer is not None:
            await recompute_ltv(session, customer)

    # Free the unit back to Available (unless it has progressed past a booking).
    unit = await session.get(Unit, booking.unit_id)
    freed = bool(unit and unit.status in (UnitStatus.booked, UnitStatus.hold))
    if freed:
        unit.status = UnitStatus.available
    await _notify(
        session, await _booking_owner_id(session, booking),
        f"Booking cancelled — ₹{refund_amount} refunded"
        + (f" (₹{payload.deduction_amount} withheld)." if payload.deduction_amount > 0 else "."),
    )
    await session.commit()
    if freed and unit:
        await realtime_manager.broadcast({
            "event": "unit.status_changed",
            "unit_id": str(unit.id),
            "status": UnitStatus.available.value,
            "project_id": str(unit.project_id),
        })
    result = await _booking_read(session, booking_id)
    # Email the customer their refund confirmation (best-effort).
    if result.customer and result.customer.email:
        await _email_service.send_refund_notice(
            result.customer.email,
            customer_name=result.customer.contact_name or "there",
            refund_amount=_fmt_inr(refund_amount),
            deduction=_fmt_inr(payload.deduction_amount) if payload.deduction_amount > 0 else None,
            unit_label=_unit_label(result),
        )
    return result


@router.post("/bookings/{booking_id}/register", response_model=BookingRead)
async def register_booking(
    booking_id: UUID,
    payload: BookingRegister,
    _: object = Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    """Record the legal registration of a confirmed booking and mark its unit
    Registered (captures deed no. + sub-registrar office + registration date)."""
    booking = await session.get(Booking, booking_id)
    if not booking or booking.is_deleted:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.status != BookingStatus.confirmed:
        raise HTTPException(status_code=409, detail="Only a confirmed booking can be registered.")

    booking.scheduled_date = payload.registration_date
    booking.registration_number = payload.registration_number
    booking.sub_registrar_office = payload.sub_registrar_office

    unit = await session.get(Unit, booking.unit_id)
    if unit is None:
        raise HTTPException(status_code=404, detail="Unit not found")
    if unit.status not in (UnitStatus.booked, UnitStatus.registered):
        raise HTTPException(status_code=409, detail=f"Unit is {unit.status.value}; it cannot be registered.")
    unit.status = UnitStatus.registered

    await _notify(
        session, await _booking_owner_id(session, booking),
        f"Unit {unit.unit_number} marked Registered.",
    )
    await session.commit()
    await realtime_manager.broadcast({
        "event": "unit.status_changed",
        "unit_id": str(unit.id),
        "status": UnitStatus.registered.value,
        "project_id": str(unit.project_id),
    })
    return await _booking_read(session, booking_id)
