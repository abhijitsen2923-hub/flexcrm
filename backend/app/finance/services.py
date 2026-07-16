"""Finance services — creation on Sold, payment recording, refunds, reporting.

Driven from `stage_transitions.create_transition`: when a Lead reaches Sold,
`SalesOrderService.create_from_lead` builds a SalesOrder + Invoice and seeds
the CommissionLedger with an `accrued` entry. Payment receipt flips the
ledger to `payable` and emits a realtime event.
"""
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError, ValidationError
from app.database.enums import (
    CommissionDirection,
    InvoiceStatus,
    PaymentStatus,
)
from app.finance.models import (
    CommissionLedger,
    Invoice,
    Payment,
    Refund,
    SalesOrder,
    SalesOrderAssist,
)
from app.finance.schemas import (
    MonthlyReportResponse,
    MonthlyRevenueRow,
    PaymentCreate,
    RefundCreate,
)
from app.models.lead import Lead
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

        # Accrue commission for the primary owner (and assists pro rata).
        if order.primary_owner_id is not None:
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
