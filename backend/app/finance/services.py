"""Finance services — creation on Sold, payment recording, refunds, reporting.

Driven from `stage_transitions.create_transition`: when a Lead reaches Sold,
`SalesOrderService.create_from_lead` builds a SalesOrder + Invoice and seeds
the CommissionLedger with an `accrued` entry. Payment receipt flips the
ledger to `payable` and emits a realtime event.
"""
from calendar import monthrange
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import selectinload

from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.core.tenancy import current_org
from app.database.enums import (
    CommissionDirection,
    ExpenseStatus,
    FinanceBusinessMode,
    FinanceCategoryKind,
    InvoiceStatus,
    PaymentStatus,
    VendorBillStatus,
)
from app.finance.category_presets import presets_for
from app.finance.gst import compute_gst
from app.finance.models import (
    BankTransaction,
    Budget,
    CommissionLedger,
    CustomerContract,
    CustomerDemand,
    DemandReceipt,
    Expense,
    FinanceAccount,
    FinanceCategory,
    FinanceSettings,
    Invoice,
    ManualIncome,
    Payment,
    Refund,
    SalesOrder,
    SalesOrderAssist,
    Vendor,
    VendorBill,
    VendorPayment,
)
from app.finance.schemas import (
    BankTransactionCreate,
    BankTransactionUpdate,
    BudgetCreate,
    BudgetUpdate,
    CustomerContractCreate,
    CustomerContractUpdate,
    CustomerDemandCreate,
    CustomerDemandUpdate,
    DemandReceiptCreate,
    ExpenseCreate,
    ExpenseFilters,
    ExpenseUpdate,
    FinanceBreakdownRow,
    FinanceAccountCreate,
    FinanceAccountUpdate,
    FinanceCategoryCreate,
    FinanceCategoryUpdate,
    FinanceSettingsUpdate,
    FinanceSummaryResponse,
    ManualIncomeCreate,
    ManualIncomeFilters,
    ManualIncomeUpdate,
    MonthlyReportResponse,
    MonthlyRevenueRow,
    PaymentCreate,
    RefundCreate,
    VendorBillCreate,
    VendorBillUpdate,
    VendorCreate,
    VendorPaymentCreate,
    VendorUpdate,
)
from app.hr.models import EmployeeProfile
from app.models.lead import Lead
from app.models.organization import Organization
from app.models.stage_transition import StageTransition
from app.models.user import User
from app.services.base import ServiceBase
from app.services.realtime import realtime_manager


# Spec §5.2 default re-attribution split for a previous owner mid-pipeline.
PREVIOUS_OWNER_ASSIST_PERCENT = 20


async def _next_sequence(session, model, attr_name: str, prefix: str, start: int = 1000) -> str:
    """Generic monotonic counter for invoice/order numbers. Suffix-formatted."""
    column = getattr(model, attr_name)
    # Pull the highest numeric suffix.
    rows = (await session.execute(select(column))).scalars().all()
    highest = start
    for value in rows:
        try:
            n = int(str(value).rsplit("-", 1)[-1])
            highest = max(highest, n)
        except (ValueError, TypeError):
            continue
    return f"{prefix}-{highest + 1}"


class SalesOrderService(ServiceBase):
    async def create_from_lead(self, lead: Lead, *, actor_id: UUID) -> SalesOrder:
        if lead.customer_id is None:
            raise ValidationError("Cannot create a SalesOrder for a lead without a Customer.")

        order_number = await _next_sequence(self.session, SalesOrder, "order_number", "SO")
        order = SalesOrder(
            order_number=order_number,
            lead_id=lead.id,
            customer_id=lead.customer_id,
            primary_owner_id=lead.assigned_to_id,
            title=lead.title,
            deal_value=lead.value or Decimal("0"),
            # Inherit currency from the lead — multi-currency support: a
            # USD-denominated lead becomes a USD-denominated sales order.
            currency=(lead.currency or "INR").upper(),
            payment_status=PaymentStatus.pending,
            closed_at=datetime.now(UTC),
            created_by_id=actor_id,
            updated_by_id=actor_id,
        )
        self.session.add(order)
        await self.session.flush()

        # Spec §5.2 re-attribution: if the lead changed owners mid-pipeline,
        # any previous owner gets a 20% assist by default. We detect this by
        # scanning the transition history for distinct performers.
        await self._apply_reattribution(order, lead)

        # Auto-invoice the full deal value.
        invoice_number = await _next_sequence(self.session, Invoice, "invoice_number", "INV")
        invoice = Invoice(
            invoice_number=invoice_number,
            sales_order_id=order.id,
            amount=order.deal_value,
            status=InvoiceStatus.issued,
            created_by_id=actor_id,
            updated_by_id=actor_id,
        )
        self.session.add(invoice)

        # Accrue commission for the primary owner (and assists pro rata) — unless
        # the lead is marked incentive-exempt ("Others / owner's reference"), in
        # which case nobody earns on this deal. The SalesOrder + Invoice are still
        # created so the revenue is recorded; only the commission accrual is skipped.
        if order.primary_owner_id is not None and not lead.incentive_exempt:
            total_assist_percent = sum(a.percent for a in order.assists)
            primary_percent = max(0, 100 - total_assist_percent)
            await self._accrue_commission(order, order.primary_owner_id, primary_percent)
            for assist in order.assists:
                await self._accrue_commission(order, assist.user_id, assist.percent)

        await self.session.flush()
        await realtime_manager.broadcast(
            {
                "event": "sales_order.created",
                "payload": {
                    "sales_order_id": str(order.id),
                    "lead_id": str(lead.id),
                    "customer_id": str(order.customer_id),
                    "owner_id": str(order.primary_owner_id) if order.primary_owner_id else None,
                    "deal_value": str(order.deal_value),
                },
            }
        )
        return order

    async def _apply_reattribution(self, order: SalesOrder, lead: Lead) -> None:
        rows = (
            await self.session.execute(
                select(StageTransition.performed_by_id)
                .where(StageTransition.lead_id == lead.id)
                .order_by(StageTransition.performed_at)
            )
        ).scalars().all()
        prior_owners = {
            uid for uid in rows
            if uid is not None and uid != order.primary_owner_id
        }
        for uid in prior_owners:
            self.session.add(
                SalesOrderAssist(
                    sales_order_id=order.id,
                    user_id=uid,
                    percent=PREVIOUS_OWNER_ASSIST_PERCENT,
                    reason="Touched lead during pipeline (re-attribution split).",
                )
            )
        await self.session.flush()
        # Refresh `order.assists` so the caller sees the new rows.
        await self.session.refresh(order, attribute_names=["assists"])

    async def _accrue_commission(self, order: SalesOrder, user_id: UUID, percent: int) -> None:
        if percent <= 0 or order.deal_value <= 0:
            return
        share = (Decimal(order.deal_value) * Decimal(percent) / Decimal(100)).quantize(Decimal("0.01"))
        self.session.add(
            CommissionLedger(
                user_id=user_id,
                sales_order_id=order.id,
                direction=CommissionDirection.accrued,
                amount=share,
                note=f"Accrued {percent}% of SO {order.order_number}",
            )
        )

    async def list_orders(self, *, filters: dict[str, object] | None = None):
        stmt = select(SalesOrder).options(selectinload(SalesOrder.assists))
        for key, value in (filters or {}).items():
            if value is None:
                continue
            stmt = stmt.where(getattr(SalesOrder, key) == value)
        stmt = stmt.order_by(SalesOrder.closed_at.desc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_order(self, order_id: UUID) -> SalesOrder:
        order = (
            await self.session.execute(
                select(SalesOrder)
                .where(SalesOrder.id == order_id)
                .options(selectinload(SalesOrder.assists), selectinload(SalesOrder.invoice))
            )
        ).scalar_one_or_none()
        if order is None:
            raise NotFoundError("Sales order not found.")
        return order


class PaymentService(ServiceBase):
    async def record_payment(self, invoice_id: UUID, payload: PaymentCreate, *, actor_id: UUID) -> Payment:
        invoice = (
            await self.session.execute(
                select(Invoice).where(Invoice.id == invoice_id).options(selectinload(Invoice.payments))
            )
        ).scalar_one_or_none()
        if invoice is None:
            raise NotFoundError("Invoice not found.")
        if invoice.status == InvoiceStatus.void:
            raise ValidationError("Cannot record payment against a voided invoice.")

        payment = Payment(
            invoice_id=invoice.id,
            amount=payload.amount,
            method=payload.method,
            txn_ref=payload.txn_ref,
            recorded_by_id=actor_id,
        )
        self.session.add(payment)
        await self.session.flush()

        # Sum all payments — flip invoice status if fully paid.
        total_paid = sum((Decimal(p.amount) for p in invoice.payments + [payment]), Decimal("0"))
        if total_paid >= Decimal(invoice.amount):
            invoice.status = InvoiceStatus.paid
            await self._mark_sales_order_paid(invoice.sales_order_id)
            await self._move_commission_to_payable(invoice.sales_order_id)

        await self.session.flush()
        await realtime_manager.broadcast(
            {
                "event": "payment.received",
                "payload": {
                    "payment_id": str(payment.id),
                    "invoice_id": str(invoice.id),
                    "amount": str(payment.amount),
                    "fully_paid": invoice.status == InvoiceStatus.paid,
                },
            }
        )
        return payment

    async def _mark_sales_order_paid(self, sales_order_id: UUID) -> None:
        order = (await self.session.execute(select(SalesOrder).where(SalesOrder.id == sales_order_id))).scalar_one()
        order.payment_status = PaymentStatus.received

    async def _move_commission_to_payable(self, sales_order_id: UUID) -> None:
        accrued = (
            await self.session.execute(
                select(CommissionLedger).where(
                    CommissionLedger.sales_order_id == sales_order_id,
                    CommissionLedger.direction == CommissionDirection.accrued,
                )
            )
        ).scalars().all()
        for entry in accrued:
            self.session.add(
                CommissionLedger(
                    user_id=entry.user_id,
                    sales_order_id=entry.sales_order_id,
                    direction=CommissionDirection.payable,
                    amount=entry.amount,
                    note=f"Payable on payment received for SO {sales_order_id}",
                )
            )


class RefundService(ServiceBase):
    async def issue_refund(self, payment_id: UUID, payload: RefundCreate, *, actor_id: UUID) -> Refund:
        payment = (
            await self.session.execute(
                select(Payment).where(Payment.id == payment_id).options(selectinload(Payment.invoice))
            )
        ).scalar_one_or_none()
        if payment is None:
            raise NotFoundError("Payment not found.")
        if payload.amount > Decimal(payment.amount):
            raise ValidationError("Refund amount cannot exceed the original payment.")

        refund = Refund(
            payment_id=payment.id,
            amount=payload.amount,
            reason=payload.reason,
            refunded_by_id=actor_id,
        )
        self.session.add(refund)
        payment.invoice.status = InvoiceStatus.refunded

        # Reverse the commission entries accrued/payable for this sales order
        # by recording reversed-direction rows (preserves the audit trail).
        sales_order_id = payment.invoice.sales_order_id
        recent_entries = (
            await self.session.execute(
                select(CommissionLedger).where(CommissionLedger.sales_order_id == sales_order_id)
            )
        ).scalars().all()
        seen_users: set[UUID] = set()
        for entry in recent_entries:
            if entry.user_id in seen_users or entry.direction == CommissionDirection.reversed:
                continue
            seen_users.add(entry.user_id)
            self.session.add(
                CommissionLedger(
                    user_id=entry.user_id,
                    sales_order_id=entry.sales_order_id,
                    direction=CommissionDirection.reversed,
                    amount=-Decimal(entry.amount),
                    note=f"Reversed: {payload.reason or 'refund issued'}",
                )
            )

        # Also reverse any still-accrued channel-partner brokerage for this deal
        # so a refunded sale doesn't leave brokerage payable. Local import avoids
        # a circular dependency at module load.
        if sales_order_id is not None:
            from app.services.channel_partners import ChannelPartnerService

            await ChannelPartnerService(self.session).reverse_brokerage_for_sales_order(
                sales_order_id, why=payload.reason or "refund issued"
            )

        await self.session.flush()
        await realtime_manager.broadcast(
            {
                "event": "refund.issued",
                "payload": {
                    "refund_id": str(refund.id),
                    "payment_id": str(payment.id),
                    "amount": str(refund.amount),
                },
            }
        )
        return refund


class FinanceReportingService(ServiceBase):
    async def monthly_report(self, month: str) -> MonthlyReportResponse:
        """`month` is "YYYY-MM"."""
        try:
            year, mon = month.split("-")
            year_i, mon_i = int(year), int(mon)
        except (ValueError, AttributeError):
            raise ValidationError("Month must be in YYYY-MM format.")

        from calendar import monthrange
        start = datetime(year_i, mon_i, 1, tzinfo=UTC)
        end_day = monthrange(year_i, mon_i)[1]
        end = datetime(year_i, mon_i, end_day, 23, 59, 59, tzinfo=UTC)

        # Per-owner revenue + collections for the month.
        rows = (
            await self.session.execute(
                select(
                    SalesOrder.primary_owner_id,
                    func.count(SalesOrder.id),
                    func.coalesce(func.sum(SalesOrder.deal_value), 0),
                )
                .where(SalesOrder.closed_at >= start, SalesOrder.closed_at <= end)
                .group_by(SalesOrder.primary_owner_id)
            )
        ).all()

        # Collections per owner — payments received in the same window.
        collections = (
            await self.session.execute(
                select(
                    SalesOrder.primary_owner_id,
                    func.coalesce(func.sum(Payment.amount), 0),
                )
                .join(Invoice, Invoice.sales_order_id == SalesOrder.id)
                .join(Payment, Payment.invoice_id == Invoice.id)
                .where(Payment.received_at >= start, Payment.received_at <= end)
                .group_by(SalesOrder.primary_owner_id)
            )
        ).all()
        collections_by_owner = {uid: total for uid, total in collections}

        # Resolve owner display names.
        owner_ids = [row[0] for row in rows if row[0] is not None]
        names_by_id: dict[UUID, str] = {}
        if owner_ids:
            users = (
                await self.session.execute(select(User).where(User.id.in_(owner_ids)))
            ).scalars().all()
            names_by_id = {u.id: f"{u.first_name} {u.last_name}" for u in users}

        output = []
        for owner_id, deals_closed, revenue in rows:
            output.append(
                MonthlyRevenueRow(
                    user_id=owner_id,
                    user_name=names_by_id.get(owner_id, "Unassigned"),
                    deals_closed=int(deals_closed),
                    revenue=Decimal(revenue or 0),
                    collections=Decimal(collections_by_owner.get(owner_id, 0)),
                )
            )
        return MonthlyReportResponse(month=month, rows=output)


# =====================================================================
# Finance vertical — Phase 1 services: settings, categories, vendors,
# expenses, vendor bills/payments.
# =====================================================================


def _apply_gst_fields(obj, data) -> None:
    """Compute + stamp the GST/amount snapshot onto an expense/vendor_bill from a
    GST input schema (any object exposing the _GstInput fields)."""
    breakdown = compute_gst(
        amount_entered=data.amount_entered,
        gst_applicable=data.gst_applicable,
        gst_rate=data.gst_rate,
        gst_treatment=data.gst_treatment,
        gst_inclusive=data.gst_inclusive,
        tds_amount=data.tds_amount,
    )
    obj.amount_entered = data.amount_entered
    obj.gst_applicable = data.gst_applicable
    obj.gst_treatment = data.gst_treatment
    obj.gst_inclusive = data.gst_inclusive
    obj.gst_rate = data.gst_rate
    obj.taxable_amount = breakdown.taxable_amount
    obj.cgst_amount = breakdown.cgst_amount
    obj.sgst_amount = breakdown.sgst_amount
    obj.igst_amount = breakdown.igst_amount
    obj.tds_amount = breakdown.tds_amount
    obj.total_amount = breakdown.total_amount
    obj.net_payable = breakdown.net_payable


class FinanceSettingsService(ServiceBase):
    async def _org(self) -> Organization:
        return (
            await self.session.execute(
                select(Organization).where(Organization.id == current_org(self.session))
            )
        ).scalar_one()

    async def get_or_create(self, *, actor_id: UUID | None = None) -> FinanceSettings:
        row = (await self.session.execute(select(FinanceSettings))).scalars().first()
        if row is None:
            row = FinanceSettings(created_by_id=actor_id, updated_by_id=actor_id)
            self.session.add(row)
            await self.session.flush()
        return row

    async def read(self) -> dict:
        row = await self.get_or_create()
        org = await self._org()
        return {
            "gst_registered": row.gst_registered,
            "gstin": row.gstin,
            "home_state_code": row.home_state_code,
            "default_place_of_supply_state": row.default_place_of_supply_state,
            "expense_approval_threshold": row.expense_approval_threshold,
            "finance_business_mode": org.finance_business_mode,
        }

    async def update(self, payload: FinanceSettingsUpdate, *, actor_id: UUID) -> dict:
        row = await self.get_or_create(actor_id=actor_id)
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(row, key, value)
        row.updated_by_id = actor_id
        await self.session.flush()
        return await self.read()


class FinanceCategoryService(ServiceBase):
    async def ensure_seeded(self, mode: FinanceBusinessMode) -> None:
        """Idempotent per-org seed of the mode's presets (unique on name+kind)."""
        existing = (
            await self.session.execute(select(FinanceCategory.name, FinanceCategory.kind))
        ).all()
        have = {(name, kind) for name, kind in existing}
        added = False
        for kind in (FinanceCategoryKind.expense, FinanceCategoryKind.income):
            for i, (name, group) in enumerate(presets_for(mode, kind)):
                if (name, kind) in have:
                    continue
                self.session.add(
                    FinanceCategory(
                        name=name, kind=kind, group_label=group,
                        source="preset", is_active=True, sort_order=i,
                    )
                )
                added = True
        if added:
            await self.session.flush()

    async def list(self, *, kind: FinanceCategoryKind | None = None, include_inactive: bool = False):
        stmt = select(FinanceCategory).where(FinanceCategory.is_deleted.is_(False))
        if kind is not None:
            stmt = stmt.where(FinanceCategory.kind == kind)
        if not include_inactive:
            stmt = stmt.where(FinanceCategory.is_active.is_(True))
        # NULL sort_order sorts last (Postgres default for ASC), then by name.
        stmt = stmt.order_by(FinanceCategory.sort_order, FinanceCategory.name)
        return list((await self.session.execute(stmt)).scalars().all())

    async def create(self, payload: FinanceCategoryCreate, *, actor_id: UUID) -> FinanceCategory:
        row = FinanceCategory(
            name=payload.name, kind=payload.kind, group_label=payload.group_label,
            source="custom", is_active=True, sort_order=payload.sort_order,
            created_by_id=actor_id, updated_by_id=actor_id,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def update(self, category_id: UUID, payload: FinanceCategoryUpdate, *, actor_id: UUID) -> FinanceCategory:
        row = (
            await self.session.execute(
                select(FinanceCategory).where(
                    FinanceCategory.id == category_id, FinanceCategory.is_deleted.is_(False)
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise NotFoundError("Category not found.")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(row, key, value)
        row.updated_by_id = actor_id
        await self.session.flush()
        return row


class VendorService(ServiceBase):
    async def list(self, *, is_active: bool | None = None, q: str | None = None):
        stmt = select(Vendor).where(Vendor.is_deleted.is_(False))
        if is_active is not None:
            stmt = stmt.where(Vendor.is_active.is_(is_active))
        if q:
            stmt = stmt.where(Vendor.name.ilike(f"%{q}%"))
        stmt = stmt.order_by(Vendor.name)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get(self, vendor_id: UUID) -> Vendor:
        row = (
            await self.session.execute(
                select(Vendor).where(Vendor.id == vendor_id, Vendor.is_deleted.is_(False))
            )
        ).scalar_one_or_none()
        if row is None:
            raise NotFoundError("Vendor not found.")
        return row

    async def create(self, payload: VendorCreate, *, actor_id: UUID) -> Vendor:
        row = Vendor(**payload.model_dump(), created_by_id=actor_id, updated_by_id=actor_id)
        self.session.add(row)
        await self.session.flush()
        return row

    async def update(self, vendor_id: UUID, payload: VendorUpdate, *, actor_id: UUID) -> Vendor:
        row = await self.get(vendor_id)
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(row, key, value)
        row.updated_by_id = actor_id
        await self.session.flush()
        return row

    async def deactivate(self, vendor_id: UUID, *, actor_id: UUID) -> None:
        row = await self.get(vendor_id)
        row.is_active = False
        row.is_deleted = True
        row.deleted_by_id = actor_id
        row.deleted_at = datetime.now(UTC)
        await self.session.flush()


class ExpenseService(ServiceBase):
    async def _get(self, expense_id: UUID) -> Expense:
        row = (
            await self.session.execute(
                select(Expense).where(Expense.id == expense_id, Expense.is_deleted.is_(False))
            )
        ).scalar_one_or_none()
        if row is None:
            raise NotFoundError("Expense not found.")
        return row

    async def get(self, expense_id: UUID) -> Expense:
        return await self._get(expense_id)

    async def list(self, filters: ExpenseFilters):
        stmt = select(Expense).where(Expense.is_deleted.is_(False))
        if filters.status is not None:
            stmt = stmt.where(Expense.status == filters.status)
        if filters.category_id is not None:
            stmt = stmt.where(Expense.category_id == filters.category_id)
        if filters.vendor_id is not None:
            stmt = stmt.where(Expense.vendor_id == filters.vendor_id)
        if filters.date_from is not None:
            stmt = stmt.where(Expense.expense_date >= filters.date_from)
        if filters.date_to is not None:
            stmt = stmt.where(Expense.expense_date <= filters.date_to)
        stmt = stmt.order_by(Expense.expense_date.desc(), Expense.created_at.desc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def create(self, payload: ExpenseCreate, *, actor_id: UUID) -> Expense:
        number = await _next_sequence(self.session, Expense, "expense_number", "EXP")
        row = Expense(
            expense_number=number, title=payload.title, notes=payload.notes,
            category_id=payload.category_id, vendor_id=payload.vendor_id, bill_id=payload.bill_id,
            project_id=payload.project_id, department=payload.department,
            expense_date=payload.expense_date, payment_mode=payload.payment_mode,
            status=ExpenseStatus.draft, created_by_id=actor_id, updated_by_id=actor_id,
        )
        _apply_gst_fields(row, payload)
        self.session.add(row)
        await self.session.flush()
        if payload.submit:
            self._do_submit(row, actor_id)
            await self.session.flush()
        await self._broadcast("expense.created", row)
        return row

    async def update(self, expense_id: UUID, payload: ExpenseUpdate, *, actor_id: UUID) -> Expense:
        row = await self._get(expense_id)
        if row.status not in (ExpenseStatus.draft, ExpenseStatus.rejected):
            raise ValidationError("Only a draft or rejected expense can be edited.")
        self._ensure_owner(row, actor_id)
        row.title = payload.title
        row.notes = payload.notes
        row.category_id = payload.category_id
        row.vendor_id = payload.vendor_id
        row.bill_id = payload.bill_id
        row.project_id = payload.project_id
        row.department = payload.department
        row.expense_date = payload.expense_date
        row.payment_mode = payload.payment_mode
        _apply_gst_fields(row, payload)
        row.updated_by_id = actor_id
        await self.session.flush()
        await self._broadcast("expense.updated", row)
        return row

    def _do_submit(self, row: Expense, actor_id: UUID) -> None:
        row.status = ExpenseStatus.submitted
        row.submitted_by_id = actor_id
        row.submitted_at = datetime.now(UTC)
        row.rejected_reason = None
        row.updated_by_id = actor_id

    @staticmethod
    def _ensure_owner(row: Expense, actor_id: UUID) -> None:
        if row.created_by_id is not None and row.created_by_id != actor_id:
            raise ValidationError("Only the person who created this expense can edit or delete it.")

    async def submit(self, expense_id: UUID, *, actor_id: UUID) -> Expense:
        row = await self._get(expense_id)
        if row.status not in (ExpenseStatus.draft, ExpenseStatus.rejected):
            raise ValidationError("Only a draft or rejected expense can be submitted.")
        self._do_submit(row, actor_id)
        await self.session.flush()
        await self._broadcast("expense.updated", row)
        return row

    async def approve(
        self,
        expense_id: UUID,
        *,
        actor_id: UUID,
        approval_threshold: Decimal | None = None,
        actor_is_high_approver: bool = True,
    ) -> Expense:
        row = await self._get(expense_id)
        if row.status != ExpenseStatus.submitted:
            raise ValidationError("Only a submitted expense can be approved.")
        # High-value gate: expenses at/above the configured threshold need an
        # approver who also holds FINANCE_SETTINGS_MANAGE (owner/accounts), not
        # just FINANCE_EXPENSE_APPROVE. threshold 0/None disables the gate.
        if (
            approval_threshold is not None
            and approval_threshold > 0
            and Decimal(row.total_amount or 0) >= approval_threshold
            and not actor_is_high_approver
        ):
            raise AuthorizationError(
                f"This expense is at or above the approval threshold "
                f"({approval_threshold:.2f}) and needs a senior approver."
            )
        row.status = ExpenseStatus.approved
        row.approved_by_id = actor_id
        row.approved_at = datetime.now(UTC)
        row.updated_by_id = actor_id
        await self.session.flush()
        await self._broadcast("expense.updated", row)
        return row

    async def reject(self, expense_id: UUID, reason: str, *, actor_id: UUID) -> Expense:
        row = await self._get(expense_id)
        if row.status != ExpenseStatus.submitted:
            raise ValidationError("Only a submitted expense can be rejected.")
        row.status = ExpenseStatus.rejected
        row.rejected_reason = reason
        row.updated_by_id = actor_id
        await self.session.flush()
        await self._broadcast("expense.updated", row)
        return row

    async def mark_paid(self, expense_id: UUID, *, paid_at, payment_mode, actor_id: UUID) -> Expense:
        row = await self._get(expense_id)
        if row.status != ExpenseStatus.approved:
            raise ValidationError("Only an approved expense can be marked paid.")
        row.status = ExpenseStatus.paid
        row.paid_at = paid_at or datetime.now(UTC).date()
        if payment_mode:
            row.payment_mode = payment_mode
        row.updated_by_id = actor_id
        await self.session.flush()
        await self._broadcast("expense.updated", row)
        return row

    async def delete(self, expense_id: UUID, *, actor_id: UUID) -> None:
        row = await self._get(expense_id)
        if row.status not in (ExpenseStatus.draft, ExpenseStatus.rejected):
            raise ValidationError("Only a draft or rejected expense can be deleted.")
        self._ensure_owner(row, actor_id)
        row.is_deleted = True
        row.deleted_by_id = actor_id
        row.deleted_at = datetime.now(UTC)
        await self.session.flush()

    async def _broadcast(self, event: str, row: Expense) -> None:
        await realtime_manager.broadcast(
            {"event": event, "payload": {"id": str(row.id), "status": row.status.value}}
        )


class VendorBillService(ServiceBase):
    async def _get(self, bill_id: UUID) -> VendorBill:
        row = (
            await self.session.execute(
                select(VendorBill)
                .where(VendorBill.id == bill_id, VendorBill.is_deleted.is_(False))
                .options(selectinload(VendorBill.payments))
            )
        ).scalar_one_or_none()
        if row is None:
            raise NotFoundError("Vendor bill not found.")
        return row

    async def get(self, bill_id: UUID) -> VendorBill:
        return await self._get(bill_id)

    async def list(self, *, vendor_id: UUID | None = None, status: VendorBillStatus | None = None):
        stmt = (
            select(VendorBill)
            .where(VendorBill.is_deleted.is_(False))
            .options(selectinload(VendorBill.payments))
        )
        if vendor_id is not None:
            stmt = stmt.where(VendorBill.vendor_id == vendor_id)
        if status is not None:
            stmt = stmt.where(VendorBill.status == status)
        stmt = stmt.order_by(VendorBill.created_at.desc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def create(self, payload: VendorBillCreate, *, actor_id: UUID) -> VendorBill:
        number = await _next_sequence(self.session, VendorBill, "bill_number", "BILL")
        row = VendorBill(
            bill_number=number, vendor_id=payload.vendor_id, vendor_invoice_no=payload.vendor_invoice_no,
            category_id=payload.category_id, project_id=payload.project_id,
            bill_date=payload.bill_date, due_date=payload.due_date, description=payload.description,
            status=VendorBillStatus.open, amount_paid=Decimal("0"),
            created_by_id=actor_id, updated_by_id=actor_id,
        )
        _apply_gst_fields(row, payload)
        self.session.add(row)
        await self.session.flush()
        await realtime_manager.broadcast({"event": "vendor_bill.created", "payload": {"id": str(row.id)}})
        return row

    async def update(self, bill_id: UUID, payload: VendorBillUpdate, *, actor_id: UUID) -> VendorBill:
        row = await self._get(bill_id)
        if row.status != VendorBillStatus.open:
            raise ValidationError("Only an open bill can be edited.")
        row.vendor_id = payload.vendor_id
        row.vendor_invoice_no = payload.vendor_invoice_no
        row.category_id = payload.category_id
        row.project_id = payload.project_id
        row.bill_date = payload.bill_date
        row.due_date = payload.due_date
        row.description = payload.description
        _apply_gst_fields(row, payload)
        row.updated_by_id = actor_id
        await self.session.flush()
        return row

    async def cancel(self, bill_id: UUID, *, actor_id: UUID) -> VendorBill:
        row = await self._get(bill_id)
        if row.status == VendorBillStatus.paid:
            raise ValidationError("A fully-paid bill cannot be cancelled.")
        row.status = VendorBillStatus.cancelled
        row.updated_by_id = actor_id
        await self.session.flush()
        await realtime_manager.broadcast({"event": "vendor_bill.updated", "payload": {"id": str(row.id)}})
        return row

    async def record_payment(self, bill_id: UUID, payload: VendorPaymentCreate, *, actor_id: UUID) -> VendorPayment:
        row = await self._get(bill_id)
        if row.status == VendorBillStatus.cancelled:
            raise ValidationError("Cannot record a payment on a cancelled bill.")
        number = await _next_sequence(self.session, VendorPayment, "payment_number", "VPAY")
        payment = VendorPayment(
            payment_number=number, bill_id=row.id, vendor_id=row.vendor_id,
            amount=payload.amount, paid_on=payload.paid_on, method=payload.method,
            txn_ref=payload.txn_ref, note=payload.note, recorded_by_id=actor_id,
        )
        self.session.add(payment)
        await self.session.flush()

        total_paid = sum((Decimal(p.amount) for p in row.payments + [payment]), Decimal("0"))
        row.amount_paid = total_paid
        if total_paid >= Decimal(row.net_payable):
            row.status = VendorBillStatus.paid
            row.paid_on = payload.paid_on
        elif total_paid > 0:
            row.status = VendorBillStatus.partially_paid
        row.updated_by_id = actor_id
        await self.session.flush()
        await realtime_manager.broadcast(
            {"event": "vendor_bill.updated", "payload": {"id": str(row.id), "status": row.status.value}}
        )
        return payment


class ManualIncomeService(ServiceBase):
    async def _get(self, income_id: UUID) -> ManualIncome:
        row = (
            await self.session.execute(
                select(ManualIncome).where(ManualIncome.id == income_id, ManualIncome.is_deleted.is_(False))
            )
        ).scalar_one_or_none()
        if row is None:
            raise NotFoundError("Income entry not found.")
        return row

    async def get(self, income_id: UUID) -> ManualIncome:
        return await self._get(income_id)

    async def list(self, filters: ManualIncomeFilters):
        stmt = select(ManualIncome).where(ManualIncome.is_deleted.is_(False))
        if filters.category_id is not None:
            stmt = stmt.where(ManualIncome.category_id == filters.category_id)
        if filters.date_from is not None:
            stmt = stmt.where(ManualIncome.income_date >= filters.date_from)
        if filters.date_to is not None:
            stmt = stmt.where(ManualIncome.income_date <= filters.date_to)
        stmt = stmt.order_by(ManualIncome.income_date.desc(), ManualIncome.created_at.desc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def create(self, payload: ManualIncomeCreate, *, actor_id: UUID) -> ManualIncome:
        number = await _next_sequence(self.session, ManualIncome, "income_number", "INC")
        row = ManualIncome(
            income_number=number, title=payload.title, category_id=payload.category_id,
            source=payload.source, project_id=payload.project_id, income_date=payload.income_date,
            payment_mode=payload.payment_mode, notes=payload.notes,
            created_by_id=actor_id, updated_by_id=actor_id,
        )
        _apply_gst_fields(row, payload)
        self.session.add(row)
        await self.session.flush()
        await realtime_manager.broadcast({"event": "income.created", "payload": {"id": str(row.id)}})
        return row

    async def update(self, income_id: UUID, payload: ManualIncomeUpdate, *, actor_id: UUID) -> ManualIncome:
        row = await self._get(income_id)
        row.title = payload.title
        row.category_id = payload.category_id
        row.source = payload.source
        row.project_id = payload.project_id
        row.income_date = payload.income_date
        row.payment_mode = payload.payment_mode
        row.notes = payload.notes
        _apply_gst_fields(row, payload)
        row.updated_by_id = actor_id
        await self.session.flush()
        return row

    async def delete(self, income_id: UUID, *, actor_id: UUID) -> None:
        row = await self._get(income_id)
        row.is_deleted = True
        row.deleted_by_id = actor_id
        row.deleted_at = datetime.now(UTC)
        await self.session.flush()


class FinanceSummaryService(ServiceBase):
    """Unified income-vs-expense / payables / GST snapshot for the finance dashboard.
    Income unions manual income + sales-order revenue (no duplication)."""

    async def _sum(self, column, *where) -> Decimal:
        value = (
            await self.session.execute(select(func.coalesce(func.sum(column), 0)).where(*where))
        ).scalar_one()
        return Decimal(value or 0)

    async def summary(self) -> FinanceSummaryResponse:
        mi_live = (ManualIncome.is_deleted.is_(False),)
        exp_live = (Expense.is_deleted.is_(False), Expense.status != ExpenseStatus.rejected)
        vb_live = (VendorBill.is_deleted.is_(False), VendorBill.status != VendorBillStatus.cancelled)

        manual_income_total = await self._sum(ManualIncome.total_amount, *mi_live)
        output_gst = await self._sum(
            ManualIncome.cgst_amount + ManualIncome.sgst_amount + ManualIncome.igst_amount, *mi_live
        )
        sales_revenue_total = await self._sum(SalesOrder.deal_value, SalesOrder.is_deleted.is_(False))

        expenses_total = await self._sum(Expense.total_amount, *exp_live)
        expenses_paid = await self._sum(Expense.total_amount, Expense.is_deleted.is_(False), Expense.status == ExpenseStatus.paid)
        expenses_gst = await self._sum(Expense.cgst_amount + Expense.sgst_amount + Expense.igst_amount, *exp_live)
        pending = (
            await self.session.execute(
                select(func.count()).select_from(Expense).where(
                    Expense.is_deleted.is_(False), Expense.status == ExpenseStatus.submitted
                )
            )
        ).scalar_one()

        bills_total = await self._sum(VendorBill.total_amount, *vb_live)
        bills_gst = await self._sum(VendorBill.cgst_amount + VendorBill.sgst_amount + VendorBill.igst_amount, *vb_live)
        payable_outstanding = await self._sum(
            VendorBill.net_payable - VendorBill.amount_paid,
            VendorBill.is_deleted.is_(False),
            VendorBill.status.in_([VendorBillStatus.open, VendorBillStatus.partially_paid]),
        )
        vendor_payments_paid = await self._sum(VendorPayment.amount)

        exp_by_cat = (
            await self.session.execute(
                select(FinanceCategory.name, func.coalesce(func.sum(Expense.total_amount), 0))
                .join(FinanceCategory, FinanceCategory.id == Expense.category_id)
                .where(*exp_live)
                .group_by(FinanceCategory.name)
                .order_by(func.sum(Expense.total_amount).desc())
            )
        ).all()
        inc_by_cat = (
            await self.session.execute(
                select(FinanceCategory.name, func.coalesce(func.sum(ManualIncome.total_amount), 0))
                .join(FinanceCategory, FinanceCategory.id == ManualIncome.category_id)
                .where(*mi_live)
                .group_by(FinanceCategory.name)
                .order_by(func.sum(ManualIncome.total_amount).desc())
            )
        ).all()

        income_total = manual_income_total + sales_revenue_total
        expense_total = expenses_total + bills_total
        expense_paid = expenses_paid + vendor_payments_paid
        input_gst = expenses_gst + bills_gst

        return FinanceSummaryResponse(
            income_total=income_total,
            manual_income_total=manual_income_total,
            sales_revenue_total=sales_revenue_total,
            expense_total=expense_total,
            expense_paid=expense_paid,
            expense_pending_approval=int(pending),
            vendor_payable_outstanding=payable_outstanding,
            output_gst=output_gst,
            input_gst=input_gst,
            net_gst=output_gst - input_gst,
            net_position=income_total - expense_paid,
            expense_by_category=[FinanceBreakdownRow(label=n, value=Decimal(v)) for n, v in exp_by_cat],
            income_by_category=[FinanceBreakdownRow(label=n, value=Decimal(v)) for n, v in inc_by_cat],
        )


class CustomerDemandService(ServiceBase):
    """Per-customer demand ledger: a contract total → ad-hoc demands → receipts.
    Balance = contract_value − total received. Statuses are plain strings."""

    async def list_contracts(self, *, customer_id: UUID | None = None):
        stmt = (
            select(CustomerContract)
            .where(CustomerContract.is_deleted.is_(False))
            .options(selectinload(CustomerContract.demands).selectinload(CustomerDemand.receipts))
        )
        if customer_id is not None:
            stmt = stmt.where(CustomerContract.customer_id == customer_id)
        stmt = stmt.order_by(CustomerContract.created_at.desc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_contract(self, contract_id: UUID) -> CustomerContract:
        row = (
            await self.session.execute(
                select(CustomerContract)
                .where(CustomerContract.id == contract_id, CustomerContract.is_deleted.is_(False))
                .options(selectinload(CustomerContract.demands).selectinload(CustomerDemand.receipts))
            )
        ).scalar_one_or_none()
        if row is None:
            raise NotFoundError("Contract not found.")
        return row

    async def create_contract(self, payload: CustomerContractCreate, *, actor_id: UUID) -> CustomerContract:
        row = CustomerContract(
            customer_id=payload.customer_id, title=payload.title, contract_value=payload.contract_value,
            currency=(payload.currency or "INR").upper(), notes=payload.notes, status="active",
            created_by_id=actor_id, updated_by_id=actor_id,
        )
        self.session.add(row)
        await self.session.flush()
        return await self.get_contract(row.id)

    async def update_contract(self, contract_id: UUID, payload: CustomerContractUpdate, *, actor_id: UUID) -> CustomerContract:
        row = await self.get_contract(contract_id)
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(row, key, value)
        row.updated_by_id = actor_id
        await self.session.flush()
        return await self.get_contract(contract_id)

    async def _get_demand(self, demand_id: UUID) -> CustomerDemand:
        row = (
            await self.session.execute(
                select(CustomerDemand)
                .where(CustomerDemand.id == demand_id, CustomerDemand.is_deleted.is_(False))
                .options(selectinload(CustomerDemand.receipts))
            )
        ).scalar_one_or_none()
        if row is None:
            raise NotFoundError("Demand not found.")
        return row

    async def get_demand(self, demand_id: UUID) -> CustomerDemand:
        return await self._get_demand(demand_id)

    async def raise_demand(self, contract_id: UUID, payload: CustomerDemandCreate, *, actor_id: UUID) -> CustomerDemand:
        contract = await self.get_contract(contract_id)
        number = await _next_sequence(self.session, CustomerDemand, "demand_number", "DMD")
        row = CustomerDemand(
            demand_number=number, contract_id=contract.id, description=payload.description,
            amount=payload.amount, due_date=payload.due_date, status="open", amount_received=Decimal("0"),
            created_by_id=actor_id, updated_by_id=actor_id,
        )
        self.session.add(row)
        await self.session.flush()
        await realtime_manager.broadcast(
            {"event": "demand.created", "payload": {"id": str(row.id), "contract_id": str(contract.id)}}
        )
        return await self._get_demand(row.id)

    async def update_demand(self, demand_id: UUID, payload: CustomerDemandUpdate, *, actor_id: UUID) -> CustomerDemand:
        row = await self._get_demand(demand_id)
        if row.status not in ("open", "partially_paid"):
            raise ValidationError("Only an open demand can be edited.")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(row, key, value)
        row.updated_by_id = actor_id
        await self.session.flush()
        return await self._get_demand(demand_id)

    async def cancel_demand(self, demand_id: UUID, *, actor_id: UUID) -> CustomerDemand:
        row = await self._get_demand(demand_id)
        if Decimal(row.amount_received or 0) > 0:
            raise ValidationError("Cannot cancel a demand that has received payments.")
        row.status = "cancelled"
        row.updated_by_id = actor_id
        await self.session.flush()
        return await self._get_demand(demand_id)

    async def record_receipt(self, demand_id: UUID, payload: DemandReceiptCreate, *, actor_id: UUID) -> DemandReceipt:
        row = await self._get_demand(demand_id)
        if row.status == "cancelled":
            raise ValidationError("Cannot record a receipt on a cancelled demand.")
        number = await _next_sequence(self.session, DemandReceipt, "receipt_number", "RCPT")
        receipt = DemandReceipt(
            receipt_number=number, demand_id=row.id, amount=payload.amount, received_on=payload.received_on,
            method=payload.method, txn_ref=payload.txn_ref, note=payload.note, recorded_by_id=actor_id,
        )
        self.session.add(receipt)
        await self.session.flush()
        total = sum((Decimal(r.amount) for r in row.receipts + [receipt]), Decimal("0"))
        row.amount_received = total
        row.status = "paid" if total >= Decimal(row.amount) else "partially_paid"
        row.updated_by_id = actor_id
        await self.session.flush()
        await realtime_manager.broadcast(
            {"event": "demand.updated", "payload": {"id": str(row.id), "status": row.status}}
        )
        return receipt


class PayrollService(ServiceBase):
    """Employee salaries → finance expenses. Salary is set on EmployeeProfile;
    a monthly run creates a submitted salary Expense per employee (idempotent by
    title so re-running a month doesn't duplicate)."""

    def _row(self, prof: EmployeeProfile, user: User) -> dict:
        return {
            "user_id": prof.user_id,
            "name": f"{user.first_name} {user.last_name}".strip() if user else "",
            "role": (user.role.value if user and user.role else None),
            "monthly_salary": prof.monthly_salary,
        }

    async def list_employees(self):
        rows = (
            await self.session.execute(
                select(EmployeeProfile, User)
                .join(User, User.id == EmployeeProfile.user_id)
                .order_by(User.first_name)
            )
        ).all()
        return [self._row(prof, user) for prof, user in rows]

    async def set_salary(self, user_id: UUID, amount: Decimal, *, actor_id: UUID) -> dict:
        prof = (
            await self.session.execute(select(EmployeeProfile).where(EmployeeProfile.user_id == user_id))
        ).scalar_one_or_none()
        if prof is None:
            prof = EmployeeProfile(user_id=user_id, monthly_salary=amount)
            self.session.add(prof)
        else:
            prof.monthly_salary = amount
        await self.session.flush()
        user = (await self.session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        return self._row(prof, user)

    async def _salary_category_id(self, actor_id: UUID) -> UUID:
        cat = (
            await self.session.execute(
                select(FinanceCategory).where(
                    FinanceCategory.name == "Salaries & Wages",
                    FinanceCategory.kind == FinanceCategoryKind.expense,
                    FinanceCategory.is_deleted.is_(False),
                )
            )
        ).scalar_one_or_none()
        if cat is None:
            cat = FinanceCategory(
                name="Salaries & Wages", kind=FinanceCategoryKind.expense, group_label="Payroll",
                source="preset", is_active=True, created_by_id=actor_id, updated_by_id=actor_id,
            )
            self.session.add(cat)
            await self.session.flush()
        return cat.id

    async def run_payroll(self, month: str, employee_ids: list[UUID] | None, *, actor_id: UUID) -> dict:
        year, mon = int(month[:4]), int(month[5:7])
        last_day = date(year, mon, monthrange(year, mon)[1])
        category_id = await self._salary_category_id(actor_id)

        query = (
            select(EmployeeProfile, User)
            .join(User, User.id == EmployeeProfile.user_id)
            .where(EmployeeProfile.monthly_salary > 0)
        )
        if employee_ids:
            query = query.where(EmployeeProfile.user_id.in_(employee_ids))
        rows = (await self.session.execute(query)).all()

        created = 0
        skipped = 0
        total = Decimal("0")
        for prof, user in rows:
            name = f"{user.first_name} {user.last_name}".strip()
            title = f"Salary — {name} — {month}"
            exists = (
                await self.session.execute(
                    select(Expense.id).where(Expense.title == title, Expense.is_deleted.is_(False))
                )
            ).scalar_one_or_none()
            if exists is not None:
                skipped += 1
                continue
            number = await _next_sequence(self.session, Expense, "expense_number", "EXP")
            amount = Decimal(prof.monthly_salary)
            self.session.add(
                Expense(
                    expense_number=number, title=title, category_id=category_id, department="Payroll",
                    expense_date=last_day, payment_mode=None, status=ExpenseStatus.submitted,
                    submitted_by_id=actor_id, submitted_at=datetime.now(UTC),
                    gst_applicable=False, amount_entered=amount, taxable_amount=amount,
                    cgst_amount=Decimal("0"), sgst_amount=Decimal("0"), igst_amount=Decimal("0"),
                    tds_amount=Decimal("0"), total_amount=amount, net_payable=amount,
                    created_by_id=actor_id, updated_by_id=actor_id,
                )
            )
            created += 1
            total += amount
        await self.session.flush()
        return {"month": month, "created": created, "skipped": skipped, "total_amount": total}


class BudgetService(ServiceBase):
    """Monthly spending budgets. `actual` (spend so far) is computed at read time
    from non-rejected expenses in the period month (+ category, if the budget is
    scoped to one) — budgets are never posted to, so there's nothing to keep in sync."""

    async def _get(self, budget_id: UUID) -> Budget:
        row = (
            await self.session.execute(
                select(Budget).where(Budget.id == budget_id, Budget.is_deleted.is_(False))
            )
        ).scalar_one_or_none()
        if row is None:
            raise NotFoundError("Budget not found.")
        return row

    async def _actual(self, period_key: str, category_id: UUID | None) -> Decimal:
        year, mon = int(period_key[:4]), int(period_key[5:7])
        first = date(year, mon, 1)
        last = date(year, mon, monthrange(year, mon)[1])
        where = [
            Expense.is_deleted.is_(False),
            Expense.status != ExpenseStatus.rejected,
            Expense.expense_date >= first,
            Expense.expense_date <= last,
        ]
        if category_id is not None:
            where.append(Expense.category_id == category_id)
        val = (
            await self.session.execute(
                select(func.coalesce(func.sum(Expense.total_amount), 0)).where(*where)
            )
        ).scalar_one()
        return Decimal(val or 0)

    async def _to_read(self, row: Budget) -> dict:
        actual = await self._actual(row.period_key, row.category_id)
        amount = Decimal(row.amount or 0)
        variance = amount - actual
        used_pct = float(actual / amount * 100) if amount > 0 else 0.0
        return {
            "id": row.id,
            "name": row.name,
            "period_key": row.period_key,
            "category_id": row.category_id,
            "category_name": row.category.name if row.category else None,
            "department": row.department,
            "amount": amount,
            "actual": actual,
            "variance": variance,
            "used_pct": round(used_pct, 1),
            "notes": row.notes,
        }

    async def list(self, *, period_key: str | None = None) -> list[dict]:
        stmt = (
            select(Budget)
            .where(Budget.is_deleted.is_(False))
            .options(selectinload(Budget.category))
        )
        if period_key:
            stmt = stmt.where(Budget.period_key == period_key)
        stmt = stmt.order_by(Budget.period_key.desc(), Budget.name)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [await self._to_read(row) for row in rows]

    async def create(self, payload: BudgetCreate, *, actor_id: UUID) -> dict:
        row = Budget(
            name=payload.name,
            period_key=payload.period_key,
            category_id=payload.category_id,
            department=payload.department,
            amount=payload.amount,
            notes=payload.notes,
            created_by_id=actor_id,
            updated_by_id=actor_id,
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row, ["category"])
        return await self._to_read(row)

    async def update(self, budget_id: UUID, payload: BudgetUpdate, *, actor_id: UUID) -> dict:
        row = await self._get(budget_id)
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(row, key, value)
        row.updated_by_id = actor_id
        await self.session.flush()
        await self.session.refresh(row, ["category"])
        return await self._to_read(row)

    async def delete(self, budget_id: UUID, *, actor_id: UUID) -> None:
        row = await self._get(budget_id)
        row.is_deleted = True
        row.deleted_by_id = actor_id
        row.deleted_at = datetime.now(UTC)
        await self.session.flush()


class FinanceAccountService(ServiceBase):
    """Bank & cash accounts. Balances are computed from opening_balance + the
    account's non-deleted transactions (current = all; cleared = reconciled only)."""

    async def _get(self, account_id: UUID) -> FinanceAccount:
        row = (
            await self.session.execute(
                select(FinanceAccount).where(
                    FinanceAccount.id == account_id, FinanceAccount.is_deleted.is_(False)
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise NotFoundError("Account not found.")
        return row

    async def _signed_sum(self, account_id: UUID, *, reconciled_only: bool) -> Decimal:
        where = [
            BankTransaction.account_id == account_id,
            BankTransaction.is_deleted.is_(False),
        ]
        if reconciled_only:
            where.append(BankTransaction.is_reconciled.is_(True))
        # Signed CASE so 'in' adds to the balance and 'out' subtracts.
        signed = func.coalesce(
            func.sum(
                case(
                    (BankTransaction.direction == "in", BankTransaction.amount),
                    else_=-BankTransaction.amount,
                )
            ),
            0,
        )
        val = (await self.session.execute(select(signed).where(*where))).scalar_one()
        return Decimal(val or 0)

    async def _unreconciled_count(self, account_id: UUID) -> int:
        val = (
            await self.session.execute(
                select(func.count()).where(
                    BankTransaction.account_id == account_id,
                    BankTransaction.is_deleted.is_(False),
                    BankTransaction.is_reconciled.is_(False),
                )
            )
        ).scalar_one()
        return int(val or 0)

    async def _to_read(self, row: FinanceAccount) -> dict:
        opening = Decimal(row.opening_balance or 0)
        current = opening + await self._signed_sum(row.id, reconciled_only=False)
        cleared = opening + await self._signed_sum(row.id, reconciled_only=True)
        return {
            "id": row.id,
            "name": row.name,
            "account_type": row.account_type,
            "opening_balance": opening,
            "currency": row.currency,
            "account_number": row.account_number,
            "ifsc": row.ifsc,
            "notes": row.notes,
            "is_active": row.is_active,
            "current_balance": current,
            "cleared_balance": cleared,
            "unreconciled_count": await self._unreconciled_count(row.id),
        }

    async def list(self, *, include_inactive: bool = False) -> list[dict]:
        stmt = select(FinanceAccount).where(FinanceAccount.is_deleted.is_(False))
        if not include_inactive:
            stmt = stmt.where(FinanceAccount.is_active.is_(True))
        stmt = stmt.order_by(FinanceAccount.name)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [await self._to_read(row) for row in rows]

    async def get(self, account_id: UUID) -> dict:
        return await self._to_read(await self._get(account_id))

    async def create(self, payload: FinanceAccountCreate, *, actor_id: UUID) -> dict:
        row = FinanceAccount(
            name=payload.name,
            account_type=payload.account_type,
            opening_balance=payload.opening_balance,
            currency=payload.currency,
            account_number=payload.account_number,
            ifsc=payload.ifsc,
            notes=payload.notes,
            created_by_id=actor_id,
            updated_by_id=actor_id,
        )
        self.session.add(row)
        await self.session.flush()
        return await self._to_read(row)

    async def update(self, account_id: UUID, payload: FinanceAccountUpdate, *, actor_id: UUID) -> dict:
        row = await self._get(account_id)
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(row, key, value)
        row.updated_by_id = actor_id
        await self.session.flush()
        return await self._to_read(row)

    async def delete(self, account_id: UUID, *, actor_id: UUID) -> None:
        row = await self._get(account_id)
        row.is_deleted = True
        row.deleted_by_id = actor_id
        row.deleted_at = datetime.now(UTC)
        await self.session.flush()


class BankTransactionService(ServiceBase):
    """Money movements on a finance account + reconciliation (mark matched to a
    bank statement)."""

    async def _get(self, txn_id: UUID) -> BankTransaction:
        row = (
            await self.session.execute(
                select(BankTransaction).where(
                    BankTransaction.id == txn_id, BankTransaction.is_deleted.is_(False)
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise NotFoundError("Transaction not found.")
        return row

    @staticmethod
    def _to_read(row: BankTransaction) -> dict:
        return {
            "id": row.id,
            "account_id": row.account_id,
            "txn_date": row.txn_date,
            "description": row.description,
            "direction": row.direction,
            "amount": row.amount,
            "reference": row.reference,
            "category_id": row.category_id,
            "category_name": row.category.name if row.category else None,
            "is_reconciled": row.is_reconciled,
            "reconciled_on": row.reconciled_on,
            "notes": row.notes,
        }

    async def list(self, account_id: UUID, *, reconciled: bool | None = None) -> list[dict]:
        stmt = (
            select(BankTransaction)
            .where(BankTransaction.account_id == account_id, BankTransaction.is_deleted.is_(False))
            .options(selectinload(BankTransaction.category))
        )
        if reconciled is not None:
            stmt = stmt.where(BankTransaction.is_reconciled.is_(reconciled))
        stmt = stmt.order_by(BankTransaction.txn_date.desc(), BankTransaction.created_at.desc())
        rows = (await self.session.execute(stmt)).scalars().all()
        return [self._to_read(row) for row in rows]

    async def create(self, account_id: UUID, payload: BankTransactionCreate, *, actor_id: UUID) -> dict:
        # Validate the account exists (and isn't deleted).
        await FinanceAccountService(self.session)._get(account_id)
        row = BankTransaction(
            account_id=account_id,
            txn_date=payload.txn_date,
            description=payload.description,
            direction=payload.direction,
            amount=payload.amount,
            reference=payload.reference,
            category_id=payload.category_id,
            notes=payload.notes,
            created_by_id=actor_id,
            updated_by_id=actor_id,
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row, ["category"])
        return self._to_read(row)

    async def update(self, txn_id: UUID, payload: BankTransactionUpdate, *, actor_id: UUID) -> dict:
        row = await self._get(txn_id)
        data = payload.model_dump(exclude_unset=True)
        # Keep reconciled_on in step with the is_reconciled flag.
        if "is_reconciled" in data:
            if data["is_reconciled"] and not row.is_reconciled:
                row.reconciled_on = datetime.now(UTC).date()
            elif not data["is_reconciled"]:
                row.reconciled_on = None
        for key, value in data.items():
            setattr(row, key, value)
        row.updated_by_id = actor_id
        await self.session.flush()
        await self.session.refresh(row, ["category"])
        return self._to_read(row)

    async def delete(self, txn_id: UUID, *, actor_id: UUID) -> None:
        row = await self._get(txn_id)
        row.is_deleted = True
        row.deleted_by_id = actor_id
        row.deleted_at = datetime.now(UTC)
        await self.session.flush()
