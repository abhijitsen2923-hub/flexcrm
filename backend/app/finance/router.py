from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissions
from app.core import storage
from app.core.permissions import PermissionCode
from app.core.tenancy import current_org
from app.database.enums import ExpenseStatus, FinanceCategoryKind, VendorBillStatus
from app.database.session import get_db_session
from app.finance.models import (
    CommissionLedger,
    Expense,
    FinanceDocument,
    Invoice,
)
from app.finance.schemas import (
    CommissionLedgerRead,
    ExpenseCreate,
    ExpenseFilters,
    ExpenseMarkPaidRequest,
    ExpenseRead,
    ExpenseRejectRequest,
    ExpenseUpdate,
    FinanceCategoryCreate,
    FinanceCategoryRead,
    FinanceCategoryUpdate,
    FinanceDocumentRead,
    FinanceSettingsRead,
    FinanceSettingsUpdate,
    FinanceSummaryResponse,
    InvoiceRead,
    ManualIncomeCreate,
    ManualIncomeFilters,
    ManualIncomeRead,
    ManualIncomeUpdate,
    MonthlyReportResponse,
    PaymentCreate,
    PaymentRead,
    RefundCreate,
    RefundRead,
    SalesOrderRead,
    VendorBillCreate,
    VendorBillRead,
    VendorBillUpdate,
    VendorCreate,
    VendorPaymentCreate,
    VendorPaymentRead,
    VendorRead,
    VendorUpdate,
)
from app.finance.services import (
    ExpenseService,
    FinanceCategoryService,
    FinanceReportingService,
    FinanceSettingsService,
    FinanceSummaryService,
    ManualIncomeService,
    PaymentService,
    RefundService,
    SalesOrderService,
    VendorBillService,
    VendorService,
)
from app.models.organization import Organization


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


# =====================================================================
# Finance vertical — Phase 1: settings, categories, vendors, expenses,
# vendor bills/payments, documents.
# =====================================================================


# ---- Settings ----

@router.get("/settings", response_model=FinanceSettingsRead)
async def get_finance_settings(
    _: object = Depends(require_permissions(PermissionCode.FINANCE_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    service = FinanceSettingsService(session)
    data = await service.read()
    await service.commit()  # persist a first-time get_or_create
    return data


@router.patch("/settings", response_model=FinanceSettingsRead)
async def update_finance_settings(
    payload: FinanceSettingsUpdate,
    current_user=Depends(require_permissions(PermissionCode.FINANCE_SETTINGS_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    service = FinanceSettingsService(session)
    data = await service.update(payload, actor_id=current_user.id)
    await service.commit()
    return data


# ---- Categories ----

@router.get("/categories", response_model=list[FinanceCategoryRead])
async def list_finance_categories(
    kind: FinanceCategoryKind | None = None,
    include_inactive: bool = False,
    _: object = Depends(require_permissions(PermissionCode.FINANCE_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    # Lazy, idempotent per-org seed from the org's business mode.
    mode = (
        await session.execute(
            select(Organization.finance_business_mode).where(Organization.id == current_org(session))
        )
    ).scalar_one()
    service = FinanceCategoryService(session)
    await service.ensure_seeded(mode)
    await service.commit()
    return await service.list(kind=kind, include_inactive=include_inactive)


@router.post("/categories", response_model=FinanceCategoryRead, status_code=status.HTTP_201_CREATED)
async def create_finance_category(
    payload: FinanceCategoryCreate,
    current_user=Depends(require_permissions(PermissionCode.FINANCE_SETTINGS_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    service = FinanceCategoryService(session)
    row = await service.create(payload, actor_id=current_user.id)
    await service.commit()
    return row


@router.patch("/categories/{category_id}", response_model=FinanceCategoryRead)
async def update_finance_category(
    category_id: UUID,
    payload: FinanceCategoryUpdate,
    current_user=Depends(require_permissions(PermissionCode.FINANCE_SETTINGS_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    service = FinanceCategoryService(session)
    row = await service.update(category_id, payload, actor_id=current_user.id)
    await service.commit()
    return row


# ---- Vendors ----

@router.get("/vendors", response_model=list[VendorRead])
async def list_vendors(
    is_active: bool | None = None,
    q: str | None = None,
    _: object = Depends(require_permissions(PermissionCode.FINANCE_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    return await VendorService(session).list(is_active=is_active, q=q)


@router.post("/vendors", response_model=VendorRead, status_code=status.HTTP_201_CREATED)
async def create_vendor(
    payload: VendorCreate,
    current_user=Depends(require_permissions(PermissionCode.FINANCE_VENDOR_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    service = VendorService(session)
    row = await service.create(payload, actor_id=current_user.id)
    await service.commit()
    return row


@router.get("/vendors/{vendor_id}", response_model=VendorRead)
async def get_vendor(
    vendor_id: UUID,
    _: object = Depends(require_permissions(PermissionCode.FINANCE_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    return await VendorService(session).get(vendor_id)


@router.patch("/vendors/{vendor_id}", response_model=VendorRead)
async def update_vendor(
    vendor_id: UUID,
    payload: VendorUpdate,
    current_user=Depends(require_permissions(PermissionCode.FINANCE_VENDOR_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    service = VendorService(session)
    row = await service.update(vendor_id, payload, actor_id=current_user.id)
    await service.commit()
    return row


@router.delete("/vendors/{vendor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vendor(
    vendor_id: UUID,
    current_user=Depends(require_permissions(PermissionCode.FINANCE_VENDOR_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    service = VendorService(session)
    await service.deactivate(vendor_id, actor_id=current_user.id)
    await service.commit()


# ---- Expenses ----

@router.get("/expenses", response_model=list[ExpenseRead])
async def list_expenses(
    filters: ExpenseFilters = Depends(),
    _: object = Depends(require_permissions(PermissionCode.FINANCE_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    return await ExpenseService(session).list(filters)


@router.post("/expenses", response_model=ExpenseRead, status_code=status.HTTP_201_CREATED)
async def create_expense(
    payload: ExpenseCreate,
    current_user=Depends(require_permissions(PermissionCode.FINANCE_EXPENSE_SUBMIT)),
    session: AsyncSession = Depends(get_db_session),
):
    service = ExpenseService(session)
    row = await service.create(payload, actor_id=current_user.id)
    await service.commit()
    return row


@router.get("/expenses/{expense_id}", response_model=ExpenseRead)
async def get_expense(
    expense_id: UUID,
    _: object = Depends(require_permissions(PermissionCode.FINANCE_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    return await ExpenseService(session).get(expense_id)


@router.patch("/expenses/{expense_id}", response_model=ExpenseRead)
async def update_expense(
    expense_id: UUID,
    payload: ExpenseUpdate,
    current_user=Depends(require_permissions(PermissionCode.FINANCE_EXPENSE_SUBMIT)),
    session: AsyncSession = Depends(get_db_session),
):
    service = ExpenseService(session)
    row = await service.update(expense_id, payload, actor_id=current_user.id)
    await service.commit()
    return row


@router.post("/expenses/{expense_id}/submit", response_model=ExpenseRead)
async def submit_expense(
    expense_id: UUID,
    current_user=Depends(require_permissions(PermissionCode.FINANCE_EXPENSE_SUBMIT)),
    session: AsyncSession = Depends(get_db_session),
):
    service = ExpenseService(session)
    row = await service.submit(expense_id, actor_id=current_user.id)
    await service.commit()
    return row


@router.post("/expenses/{expense_id}/approve", response_model=ExpenseRead)
async def approve_expense(
    expense_id: UUID,
    current_user=Depends(require_permissions(PermissionCode.FINANCE_EXPENSE_APPROVE)),
    session: AsyncSession = Depends(get_db_session),
):
    service = ExpenseService(session)
    row = await service.approve(expense_id, actor_id=current_user.id)
    await service.commit()
    return row


@router.post("/expenses/{expense_id}/reject", response_model=ExpenseRead)
async def reject_expense(
    expense_id: UUID,
    payload: ExpenseRejectRequest,
    current_user=Depends(require_permissions(PermissionCode.FINANCE_EXPENSE_APPROVE)),
    session: AsyncSession = Depends(get_db_session),
):
    service = ExpenseService(session)
    row = await service.reject(expense_id, payload.reason, actor_id=current_user.id)
    await service.commit()
    return row


@router.post("/expenses/{expense_id}/mark-paid", response_model=ExpenseRead)
async def mark_expense_paid(
    expense_id: UUID,
    payload: ExpenseMarkPaidRequest,
    current_user=Depends(require_permissions(PermissionCode.FINANCE_RECORD_PAYMENT)),
    session: AsyncSession = Depends(get_db_session),
):
    service = ExpenseService(session)
    row = await service.mark_paid(
        expense_id, paid_at=payload.paid_at, payment_mode=payload.payment_mode, actor_id=current_user.id
    )
    await service.commit()
    return row


@router.delete("/expenses/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_expense(
    expense_id: UUID,
    current_user=Depends(require_permissions(PermissionCode.FINANCE_EXPENSE_SUBMIT)),
    session: AsyncSession = Depends(get_db_session),
):
    service = ExpenseService(session)
    await service.delete(expense_id, actor_id=current_user.id)
    await service.commit()


# ---- Vendor bills + payments ----

@router.get("/vendor-bills", response_model=list[VendorBillRead])
async def list_vendor_bills(
    vendor_id: UUID | None = None,
    bill_status: VendorBillStatus | None = Query(default=None, alias="status"),
    _: object = Depends(require_permissions(PermissionCode.FINANCE_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    return await VendorBillService(session).list(vendor_id=vendor_id, status=bill_status)


@router.post("/vendor-bills", response_model=VendorBillRead, status_code=status.HTTP_201_CREATED)
async def create_vendor_bill(
    payload: VendorBillCreate,
    current_user=Depends(require_permissions(PermissionCode.FINANCE_VENDOR_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    service = VendorBillService(session)
    row = await service.create(payload, actor_id=current_user.id)
    await service.commit()
    return await service.get(row.id)


@router.get("/vendor-bills/{bill_id}", response_model=VendorBillRead)
async def get_vendor_bill(
    bill_id: UUID,
    _: object = Depends(require_permissions(PermissionCode.FINANCE_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    return await VendorBillService(session).get(bill_id)


@router.patch("/vendor-bills/{bill_id}", response_model=VendorBillRead)
async def update_vendor_bill(
    bill_id: UUID,
    payload: VendorBillUpdate,
    current_user=Depends(require_permissions(PermissionCode.FINANCE_VENDOR_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    service = VendorBillService(session)
    await service.update(bill_id, payload, actor_id=current_user.id)
    await service.commit()
    return await service.get(bill_id)


@router.post("/vendor-bills/{bill_id}/cancel", response_model=VendorBillRead)
async def cancel_vendor_bill(
    bill_id: UUID,
    current_user=Depends(require_permissions(PermissionCode.FINANCE_VENDOR_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    service = VendorBillService(session)
    await service.cancel(bill_id, actor_id=current_user.id)
    await service.commit()
    return await service.get(bill_id)


@router.post(
    "/vendor-bills/{bill_id}/payments",
    response_model=VendorPaymentRead,
    status_code=status.HTTP_201_CREATED,
)
async def record_vendor_payment(
    bill_id: UUID,
    payload: VendorPaymentCreate,
    current_user=Depends(require_permissions(PermissionCode.FINANCE_RECORD_PAYMENT)),
    session: AsyncSession = Depends(get_db_session),
):
    service = VendorBillService(session)
    payment = await service.record_payment(bill_id, payload, actor_id=current_user.id)
    await service.commit()
    return payment


@router.get("/vendor-bills/{bill_id}/payments", response_model=list[VendorPaymentRead])
async def list_vendor_payments(
    bill_id: UUID,
    _: object = Depends(require_permissions(PermissionCode.FINANCE_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    bill = await VendorBillService(session).get(bill_id)
    return bill.payments


# ---- Documents (bills / receipts / proofs) ----

@router.post("/documents", response_model=FinanceDocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_finance_document(
    file: UploadFile = File(...),
    owner_type: str = Form(...),
    owner_id: UUID = Form(...),
    doc_type: str | None = Form(default=None),
    current_user=Depends(require_permissions(PermissionCode.FINANCE_EXPENSE_SUBMIT)),
    session: AsyncSession = Depends(get_db_session),
):
    if owner_type not in ("expense", "vendor_bill"):
        raise HTTPException(status_code=400, detail="owner_type must be 'expense' or 'vendor_bill'.")
    data = await file.read()
    doc = FinanceDocument(
        owner_type=owner_type,
        owner_id=owner_id,
        doc_type=doc_type,
        file_name=file.filename,
        content_type=file.content_type,
        file_path="",
        uploaded_by_id=current_user.id,
    )
    session.add(doc)
    await session.flush()  # allocate doc.id for the storage key
    key = storage.finance_doc_key(current_org(session), owner_type, owner_id, doc.id, file.filename or "file")
    storage.put_object(key, data, file.content_type)  # raises 503 if storage unconfigured
    doc.file_path = key
    await session.commit()
    return doc


@router.get("/documents", response_model=list[FinanceDocumentRead])
async def list_finance_documents(
    owner_type: str,
    owner_id: UUID,
    _: object = Depends(require_permissions(PermissionCode.FINANCE_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    stmt = (
        select(FinanceDocument)
        .where(FinanceDocument.owner_type == owner_type, FinanceDocument.owner_id == owner_id)
        .order_by(FinanceDocument.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


@router.get("/documents/{doc_id}/download")
async def download_finance_document(
    doc_id: UUID,
    _: object = Depends(require_permissions(PermissionCode.FINANCE_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    doc = (
        await session.execute(select(FinanceDocument).where(FinanceDocument.id == doc_id))
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return {"url": storage.presigned_get_url(doc.file_path)}


# ---- Manual income (Phase 2) ----

@router.get("/income", response_model=list[ManualIncomeRead])
async def list_income(
    filters: ManualIncomeFilters = Depends(),
    _: object = Depends(require_permissions(PermissionCode.FINANCE_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    return await ManualIncomeService(session).list(filters)


@router.post("/income", response_model=ManualIncomeRead, status_code=status.HTTP_201_CREATED)
async def create_income(
    payload: ManualIncomeCreate,
    current_user=Depends(require_permissions(PermissionCode.FINANCE_RECORD_PAYMENT)),
    session: AsyncSession = Depends(get_db_session),
):
    service = ManualIncomeService(session)
    row = await service.create(payload, actor_id=current_user.id)
    await service.commit()
    return row


@router.get("/income/{income_id}", response_model=ManualIncomeRead)
async def get_income(
    income_id: UUID,
    _: object = Depends(require_permissions(PermissionCode.FINANCE_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    return await ManualIncomeService(session).get(income_id)


@router.patch("/income/{income_id}", response_model=ManualIncomeRead)
async def update_income(
    income_id: UUID,
    payload: ManualIncomeUpdate,
    current_user=Depends(require_permissions(PermissionCode.FINANCE_RECORD_PAYMENT)),
    session: AsyncSession = Depends(get_db_session),
):
    service = ManualIncomeService(session)
    row = await service.update(income_id, payload, actor_id=current_user.id)
    await service.commit()
    return row


@router.delete("/income/{income_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_income(
    income_id: UUID,
    current_user=Depends(require_permissions(PermissionCode.FINANCE_RECORD_PAYMENT)),
    session: AsyncSession = Depends(get_db_session),
):
    service = ManualIncomeService(session)
    await service.delete(income_id, actor_id=current_user.id)
    await service.commit()


# ---- Unified finance dashboard summary (Phase 2) ----

@router.get("/summary", response_model=FinanceSummaryResponse)
async def finance_summary(
    _: object = Depends(require_permissions(PermissionCode.FINANCE_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    return await FinanceSummaryService(session).summary()
