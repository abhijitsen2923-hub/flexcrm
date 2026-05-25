from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissions
from app.core.permissions import PermissionCode
from app.database.session import get_db_session
from app.finance.schemas import (
    CommissionLedgerRead,
    InvoiceRead,
    MonthlyReportResponse,
    PaymentCreate,
    PaymentRead,
    RefundCreate,
    RefundRead,
    SalesOrderRead,
)
from app.finance.services import (
    FinanceReportingService,
    PaymentService,
    RefundService,
    SalesOrderService,
)
from sqlalchemy import select
from app.finance.models import CommissionLedger, Invoice


router = APIRouter()


@router.get("/sales-orders", response_model=list[SalesOrderRead])
async def list_sales_orders(
    customer_id: UUID | None = None,
    primary_owner_id: UUID | None = None,
    _: object = Depends(require_permissions(PermissionCode.FINANCE_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    return await SalesOrderService(session).list_orders(
        filters={"customer_id": customer_id, "primary_owner_id": primary_owner_id}
    )


@router.get("/sales-orders/{order_id}", response_model=SalesOrderRead)
async def get_sales_order(
    order_id: UUID,
    _: object = Depends(require_permissions(PermissionCode.FINANCE_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    return await SalesOrderService(session).get_order(order_id)


@router.get("/invoices", response_model=list[InvoiceRead])
async def list_invoices(
    sales_order_id: UUID | None = None,
    _: object = Depends(require_permissions(PermissionCode.FINANCE_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    stmt = select(Invoice)
    if sales_order_id:
        stmt = stmt.where(Invoice.sales_order_id == sales_order_id)
    stmt = stmt.order_by(Invoice.created_at.desc())
    return list((await session.execute(stmt)).scalars().all())


@router.post(
    "/invoices/{invoice_id}/payments",
    response_model=PaymentRead,
    status_code=status.HTTP_201_CREATED,
)
async def record_payment(
    invoice_id: UUID,
    payload: PaymentCreate,
    current_user=Depends(require_permissions(PermissionCode.FINANCE_RECORD_PAYMENT)),
    session: AsyncSession = Depends(get_db_session),
):
    service = PaymentService(session)
    payment = await service.record_payment(invoice_id, payload, actor_id=current_user.id)
    await service.commit()
    return payment


@router.post(
    "/payments/{payment_id}/refund",
    response_model=RefundRead,
    status_code=status.HTTP_201_CREATED,
)
async def issue_refund(
    payment_id: UUID,
    payload: RefundCreate,
    current_user=Depends(require_permissions(PermissionCode.FINANCE_REFUND)),
    session: AsyncSession = Depends(get_db_session),
):
    service = RefundService(session)
    refund = await service.issue_refund(payment_id, payload, actor_id=current_user.id)
    await service.commit()
    return refund


@router.get("/commission-ledger", response_model=list[CommissionLedgerRead])
async def list_commission_ledger(
    user_id: UUID | None = None,
    _: object = Depends(require_permissions(PermissionCode.FINANCE_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    stmt = select(CommissionLedger)
    if user_id:
        stmt = stmt.where(CommissionLedger.user_id == user_id)
    stmt = stmt.order_by(CommissionLedger.recorded_at.desc())
    return list((await session.execute(stmt)).scalars().all())


@router.get("/reports/monthly", response_model=MonthlyReportResponse)
async def monthly_report(
    month: str = Query(..., description="YYYY-MM"),
    _: object = Depends(require_permissions(PermissionCode.REPORTS_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    return await FinanceReportingService(session).monthly_report(month)
