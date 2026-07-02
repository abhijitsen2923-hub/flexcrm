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
from app.finance.models import SalesOrder
from app.models.customer import Customer
from app.models.lead import Lead
from app.models.organization import Organization


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
