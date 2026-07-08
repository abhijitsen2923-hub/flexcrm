"""Real estate API routes — inventory, site visits, bookings."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_permissions
from app.core.exceptions import NotFoundError
from app.core.permissions import PermissionCode
from app.database.enums import BookingStatus, UnitStatus, UnitType
from app.database.session import get_db_session
from app.models.customer import Customer
from app.real_estate.documents import render_booking_document
from app.real_estate.models import (
    Booking,
    BookingKycDoc,
    PaymentSchedule,
    Project,
    SiteVisit,
    Tower,
    Unit,
)
from app.real_estate.schemas import (
    BookingCreate,
    BookingKycDocCreate,
    BookingKycDocRead,
    BookingRead,
    BookingStepAdvance,
    CollectionLedgerEntry,
    PaymentScheduleRead,
    PricingUpdate,
    ProjectCreate,
    ProjectRead,
    ProjectWithTowersRead,
    SiteVisitCreate,
    SiteVisitRead,
    SiteVisitUpdate,
    TowerCreate,
    TowerRead,
    UnitBatchCreate,
    UnitRead,
    UnitStatusUpdate,
)
from app.services.realtime import realtime_manager

router = APIRouter()


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
        .options(
            selectinload(Project.towers).selectinload(Tower.units)
        )
        .order_by(Project.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


@router.post("/inventory/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    _: object = Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    project = Project(**payload.model_dump())
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


@router.get("/inventory/projects/{project_id}", response_model=ProjectWithTowersRead)
async def get_project(
    project_id: UUID,
    _: object = Depends(require_permissions(PermissionCode.LEAD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    stmt = (
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.towers).selectinload(Tower.units))
    )
    project = (await session.execute(stmt)).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


# ---------------------------------------------------------------------------
# Inventory — towers + units (creation)
# ---------------------------------------------------------------------------

# Default unit-number prefix per type when the caller doesn't supply one.
_TYPE_PREFIX = {
    UnitType.residential: "R",
    UnitType.parking: "P",
    UnitType.shop: "S",
    UnitType.godown: "G",
}


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
    if not project:
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
    tower = await session.get(Tower, tower_id)
    if not tower:
        raise HTTPException(status_code=404, detail="Tower not found")

    prefix = (payload.unit_prefix or _TYPE_PREFIX.get(payload.unit_type, "U")).strip()
    for fu in payload.floors:
        for n in range(1, fu.count + 1):
            session.add(
                Unit(
                    project_id=tower.project_id,
                    tower_id=tower.id,
                    floor=fu.floor,
                    unit_number=f"{prefix}{fu.floor}{n:02d}",
                    unit_type=payload.unit_type.value,
                    area=payload.area,
                    base_price=payload.base_price,
                    area_unit=payload.area_unit,
                    facing=payload.facing,
                    status=UnitStatus.available,
                )
            )
    await session.commit()
    # Return the tower's units freshly loaded (avoids per-object refresh after commit).
    stmt = (
        select(Unit)
        .where(Unit.tower_id == tower_id)
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
# Site visits
# ---------------------------------------------------------------------------

@router.get("/site-visits", response_model=list[SiteVisitRead])
async def list_site_visits(
    project_id: UUID | None = Query(default=None),
    lead_id: UUID | None = Query(default=None),
    _: object = Depends(require_permissions(PermissionCode.LEAD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    stmt = select(SiteVisit).order_by(SiteVisit.scheduled_at.desc())
    if project_id:
        stmt = stmt.where(SiteVisit.project_id == project_id)
    if lead_id:
        stmt = stmt.where(SiteVisit.lead_id == lead_id)
    return list((await session.execute(stmt)).scalars().all())


@router.post("/site-visits", response_model=SiteVisitRead, status_code=status.HTTP_201_CREATED)
async def create_site_visit(
    payload: SiteVisitCreate,
    _: object = Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    visit = SiteVisit(**payload.model_dump())
    session.add(visit)
    await session.commit()
    await session.refresh(visit)
    return visit


@router.patch("/site-visits/{visit_id}", response_model=SiteVisitRead)
async def update_site_visit(
    visit_id: UUID,
    payload: SiteVisitUpdate,
    _: object = Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    visit = await session.get(SiteVisit, visit_id)
    if not visit:
        raise HTTPException(status_code=404, detail="Site visit not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(visit, field, value)
    await session.commit()
    await session.refresh(visit)
    return visit


# ---------------------------------------------------------------------------
# Bookings — collection-ledger MUST be registered before /{booking_id}
# ---------------------------------------------------------------------------

@router.get("/bookings/collection-ledger", response_model=list[CollectionLedgerEntry])
async def collection_ledger(
    _: object = Depends(require_permissions(PermissionCode.FINANCE_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    stmt = (
        select(
            PaymentSchedule,
            Booking.status,
            Unit.unit_number,
            Project.name.label("project_name"),
        )
        .join(Booking, PaymentSchedule.booking_id == Booking.id)
        .join(Unit, Booking.unit_id == Unit.id)
        .join(Project, Unit.project_id == Project.id)
        .where(Booking.is_deleted.is_(False))
        .order_by(PaymentSchedule.due_date)
    )
    rows = (await session.execute(stmt)).all()
    return [
        CollectionLedgerEntry(
            payment_schedule_id=ps.id,
            booking_id=ps.booking_id,
            installment_name=ps.installment_name,
            due_date=ps.due_date,
            demand_amount=ps.demand_amount,
            paid_amount=ps.paid_amount,
            outstanding=ps.outstanding,
            is_overdue=ps.is_overdue,
            project_name=project_name,
            unit_number=unit_number,
            status=b_status,
        )
        for ps, b_status, unit_number, project_name in rows
    ]


@router.get("/bookings", response_model=list[BookingRead])
async def list_bookings(
    unit_id: UUID | None = Query(default=None),
    customer_id: UUID | None = Query(default=None),
    booking_status: str | None = Query(default=None, alias="status"),
    _: object = Depends(require_permissions(PermissionCode.LEAD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    stmt = (
        select(Booking)
        .options(
            selectinload(Booking.kyc_documents),
            selectinload(Booking.payment_schedules),
        )
        .where(Booking.is_deleted.is_(False))
        .order_by(Booking.created_at.desc())
    )
    if unit_id:
        stmt = stmt.where(Booking.unit_id == unit_id)
    if customer_id:
        stmt = stmt.where(Booking.customer_id == customer_id)
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
    await session.commit()
    stmt = (
        select(Booking)
        .where(Booking.id == booking.id)
        .options(selectinload(Booking.kyc_documents), selectinload(Booking.payment_schedules))
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
        .options(selectinload(Booking.kyc_documents), selectinload(Booking.payment_schedules))
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

    # Final step confirms the booking and marks the unit as Booked (unless it's
    # already further along, e.g. registered/sold). Capture ids before commit so
    # the post-commit broadcast doesn't trigger a lazy load on an expired object.
    booked_unit: tuple[str, str] | None = None
    if step == 4 and booking.status != BookingStatus.confirmed:
        booking.status = BookingStatus.confirmed
        unit = await session.get(Unit, booking.unit_id)
        if unit is not None and unit.status in (UnitStatus.available, UnitStatus.hold):
            unit.status = UnitStatus.booked
            booked_unit = (str(unit.id), str(unit.project_id))
    await session.commit()
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
        .options(selectinload(Booking.kyc_documents), selectinload(Booking.payment_schedules))
    )
    return (await session.execute(stmt)).scalar_one()


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
        .options(selectinload(Booking.kyc_documents), selectinload(Booking.payment_schedules))
    )
    return (await session.execute(stmt)).scalar_one()


@router.get("/bookings/{booking_id}/documents/{doc_type}")
async def get_booking_document_url(
    booking_id: UUID,
    doc_type: str,
    _: object = Depends(require_permissions(PermissionCode.LEAD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
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


@router.post(
    "/bookings/{booking_id}/kyc",
    response_model=BookingKycDocRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_booking_kyc(
    booking_id: UUID,
    payload: BookingKycDocCreate,
    _: object = Depends(require_permissions(PermissionCode.LEAD_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    booking = await session.get(Booking, booking_id)
    if not booking or booking.is_deleted:
        raise HTTPException(status_code=404, detail="Booking not found")
    doc = BookingKycDoc(booking_id=booking_id, **payload.model_dump())
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    return doc
