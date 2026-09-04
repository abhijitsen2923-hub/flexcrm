"""CSV exports for Leads, Customers, Sales Orders (Phase 6).

Returns a text/csv response that the browser opens as a download. Filter
support is intentionally minimal — the same list-page filters are echoed
as query params.
"""
import csv
import io
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_permissions
from app.core.lead_csv import CsvColumn, columns_for
from app.core.permissions import PermissionCode
from app.core.tenancy import current_org
from app.database.enums import LeadIndustry
from app.database.session import get_db_session
from app.finance.models import Expense, FinanceCategory, ManualIncome, SalesOrder, Vendor, VendorBill
from app.models.customer import Customer
from app.models.lead import Lead
from app.models.organization import Organization
from app.real_estate.models import Booking, Tower, Unit


router = APIRouter()


def _csv_response(filename: str, rows: list[list[str]], header: list[str]) -> StreamingResponse:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows(rows)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _lead_cell(lead: Lead, col: CsvColumn) -> str:
    if col.key == "owner_email":
        return lead.assigned_to.email if lead.assigned_to else ""
    attr = "stage_code" if col.key == "stage" else col.key
    value = getattr(lead, attr, None)
    if value is None:
        return ""
    if hasattr(value, "value"):  # enum
        return str(value.value)
    if hasattr(value, "isoformat"):  # date/datetime
        return value.isoformat()
    return str(value)


@router.get("/leads.csv")
async def export_leads(
    industry: LeadIndustry | None = None,
    _: object = Depends(require_permissions(PermissionCode.EXPORT_DATA, PermissionCode.LEAD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    stmt = (
        select(Lead)
        .where(Lead.is_deleted.is_(False))
        .options(selectinload(Lead.customer), selectinload(Lead.assigned_to))
    )
    if industry is not None:
        stmt = stmt.where(Lead.industry == industry)
    stmt = stmt.order_by(Lead.lead_number)
    leads = (await session.execute(stmt)).scalars().all()

    # Column layout follows the tenant's vertical (same source of truth as the
    # import template) so real-estate exports include property/budget columns.
    vertical = industry
    if vertical is None:
        org_id = current_org(session)
        if org_id is not None:
            org = (
                await session.execute(select(Organization).where(Organization.id == org_id))
            ).scalar_one_or_none()
            vertical = org.business_type if org else None
    cols = columns_for(vertical)

    header = ["lead_number", "industry", *[c.header for c in cols], "created_at"]
    rows = [
        [
            str(lead.lead_number), lead.industry.value,
            *[_lead_cell(lead, c) for c in cols],
            lead.created_at.isoformat(),
        ]
        for lead in leads
    ]
    return _csv_response(f"leads-{datetime.utcnow().date()}.csv", rows, header)


@router.get("/customers.csv")
async def export_customers(
    _: object = Depends(require_permissions(PermissionCode.EXPORT_DATA, PermissionCode.CUSTOMER_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    stmt = (
        select(Customer)
        .where(Customer.is_deleted.is_(False))
        .order_by(Customer.created_at.desc())
    )
    customers = (await session.execute(stmt)).scalars().all()
    header = [
        "customer_number", "company_name", "contact_name", "email", "phone",
        "lifecycle_stage", "status", "ltv", "source_lead_id", "created_at",
    ]
    rows = [
        [
            str(c.customer_number or ""), c.company_name, c.contact_name,
            c.email or "", c.phone or "", c.lifecycle_stage.value, c.status.value,
            str(c.ltv), str(c.source_lead_id or ""), c.created_at.isoformat(),
        ]
        for c in customers
    ]
    return _csv_response(f"customers-{datetime.utcnow().date()}.csv", rows, header)


@router.get("/sales-orders.csv")
async def export_sales_orders(
    _: object = Depends(require_permissions(PermissionCode.EXPORT_DATA, PermissionCode.FINANCE_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    stmt = (
        select(SalesOrder)
        .where(SalesOrder.is_deleted.is_(False))
        .order_by(SalesOrder.closed_at.desc())
    )
    orders = (await session.execute(stmt)).scalars().all()
    header = [
        "order_number", "lead_id", "customer_id", "primary_owner_id", "title",
        "deal_value", "currency", "payment_status", "closed_at",
    ]
    rows = [
        [
            o.order_number, str(o.lead_id or ""), str(o.customer_id),
            str(o.primary_owner_id or ""), o.title, str(o.deal_value),
            o.currency, o.payment_status.value, o.closed_at.isoformat(),
        ]
        for o in orders
    ]
    return _csv_response(f"sales-orders-{datetime.utcnow().date()}.csv", rows, header)


@router.get("/inventory.csv")
async def export_inventory(
    _: object = Depends(require_permissions(PermissionCode.EXPORT_DATA, PermissionCode.LEAD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    stmt = (
        select(Unit)
        .where(Unit.is_deleted.is_(False))
        .options(selectinload(Unit.tower).selectinload(Tower.project))
        .order_by(Unit.created_at.desc())
    )
    units = (await session.execute(stmt)).scalars().all()
    header = [
        "project", "tower", "unit_number", "floor", "unit_type",
        "area", "area_unit", "base_price", "status", "facing",
    ]
    rows = [
        [
            u.project_name or "", u.tower_name or "", u.unit_number, str(u.floor),
            u.unit_type, str(u.area), u.area_unit, str(u.base_price),
            u.status.value, u.facing or "",
        ]
        for u in units
    ]
    return _csv_response(f"inventory-{datetime.utcnow().date()}.csv", rows, header)


@router.get("/bookings.csv")
async def export_bookings(
    _: object = Depends(require_permissions(PermissionCode.EXPORT_DATA, PermissionCode.LEAD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    stmt = (
        select(Booking)
        .where(Booking.is_deleted.is_(False))
        .options(
            selectinload(Booking.unit).selectinload(Unit.tower).selectinload(Tower.project),
            selectinload(Booking.customer),
        )
        .order_by(Booking.created_at.desc())
    )
    bookings = (await session.execute(stmt)).scalars().all()
    header = [
        "booking_id", "status", "customer", "project", "tower", "unit_number",
        "total_consideration", "registration_date", "registration_number",
        "sub_registrar_office", "created_at",
    ]
    rows = []
    for b in bookings:
        unit = b.unit
        snap = b.pricing_snapshot if isinstance(b.pricing_snapshot, dict) else {}
        total = snap.get("total")
        rows.append([
            str(b.id), b.status.value,
            b.customer.contact_name if b.customer else "",
            (unit.project_name or "") if unit else "",
            (unit.tower_name or "") if unit else "",
            unit.unit_number if unit else "",
            str(total) if total is not None else "",
            b.scheduled_date.isoformat() if b.scheduled_date else "",
            b.registration_number or "",
            b.sub_registrar_office or "",
            b.created_at.isoformat(),
        ])
    return _csv_response(f"bookings-{datetime.utcnow().date()}.csv", rows, header)


# --- Finance exports (Phase 2) ---

def _m(value) -> str:
    return "" if value is None else str(value)


def _dt(value) -> str:
    return value.isoformat() if value is not None else ""


@router.get("/finance-expenses.csv")
async def export_finance_expenses(
    _: object = Depends(require_permissions(PermissionCode.EXPORT_DATA, PermissionCode.FINANCE_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    cats = {c.id: c.name for c in (await session.execute(select(FinanceCategory))).scalars().all()}
    vends = {v.id: v.name for v in (await session.execute(select(Vendor))).scalars().all()}
    items = (
        await session.execute(
            select(Expense).where(Expense.is_deleted.is_(False)).order_by(Expense.expense_date.desc())
        )
    ).scalars().all()
    header = ["Expense #", "Date", "Title", "Category", "Vendor", "Status",
              "Amount", "Taxable", "CGST", "SGST", "IGST", "TDS", "Total", "Net payable"]
    rows = [[
        e.expense_number, _dt(e.expense_date), e.title, cats.get(e.category_id, ""),
        vends.get(e.vendor_id, "") if e.vendor_id else "", e.status.value,
        _m(e.amount_entered), _m(e.taxable_amount), _m(e.cgst_amount), _m(e.sgst_amount),
        _m(e.igst_amount), _m(e.tds_amount), _m(e.total_amount), _m(e.net_payable),
    ] for e in items]
    return _csv_response(f"finance-expenses-{datetime.utcnow().date()}.csv", rows, header)


@router.get("/finance-income.csv")
async def export_finance_income(
    _: object = Depends(require_permissions(PermissionCode.EXPORT_DATA, PermissionCode.FINANCE_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    cats = {c.id: c.name for c in (await session.execute(select(FinanceCategory))).scalars().all()}
    items = (
        await session.execute(
            select(ManualIncome).where(ManualIncome.is_deleted.is_(False)).order_by(ManualIncome.income_date.desc())
        )
    ).scalars().all()
    header = ["Income #", "Date", "Title", "Category", "Source",
              "Amount", "Taxable", "CGST", "SGST", "IGST", "TDS", "Total"]
    rows = [[
        i.income_number, _dt(i.income_date), i.title, cats.get(i.category_id, ""), i.source or "",
        _m(i.amount_entered), _m(i.taxable_amount), _m(i.cgst_amount), _m(i.sgst_amount),
        _m(i.igst_amount), _m(i.tds_amount), _m(i.total_amount),
    ] for i in items]
    return _csv_response(f"finance-income-{datetime.utcnow().date()}.csv", rows, header)


@router.get("/vendor-bills.csv")
async def export_vendor_bills(
    _: object = Depends(require_permissions(PermissionCode.EXPORT_DATA, PermissionCode.FINANCE_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    vends = {v.id: v.name for v in (await session.execute(select(Vendor))).scalars().all()}
    items = (
        await session.execute(
            select(VendorBill).where(VendorBill.is_deleted.is_(False)).order_by(VendorBill.created_at.desc())
        )
    ).scalars().all()
    header = ["Bill #", "Vendor", "Vendor invoice #", "Bill date", "Due date", "Status",
              "Taxable", "Total", "Amount paid", "Outstanding"]
    rows = [[
        b.bill_number, vends.get(b.vendor_id, ""), b.vendor_invoice_no or "", _dt(b.bill_date), _dt(b.due_date),
        b.status.value, _m(b.taxable_amount), _m(b.total_amount), _m(b.amount_paid),
        _m((b.net_payable or 0) - (b.amount_paid or 0)),
    ] for b in items]
    return _csv_response(f"vendor-bills-{datetime.utcnow().date()}.csv", rows, header)
