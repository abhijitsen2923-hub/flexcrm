"""Channel-partner (broker) service — profiles, roster stats, partner dashboard,
lead submission, and brokerage accrual."""
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.core.tenancy import current_org
from app.database.enums import LeadIndustry, UserRole, UserStatus
from app.models.channel_partner import BrokeragePayout, ChannelPartner
from app.models.lead import Lead
from app.models.user import User
from app.services.email import EmailService
from app.schemas.channel_partner import (
    ChannelPartnerCreate,
    ChannelPartnerStats,
    ChannelPartnerUpdate,
    PartnerLeadSubmit,
    PartnerStageCount,
)
from app.schemas.lead import LeadCreate
from app.services.base import ServiceBase
from app.services.leads import LeadService

SOLD = "sold"
LOST = "lost"


def _humanize(stage_code: str) -> str:
    return stage_code.replace("_", " ").title()


class ChannelPartnerService(ServiceBase):
    # --- profiles ----------------------------------------------------------
    async def create_partner(self, payload: ChannelPartnerCreate, *, actor_id: UUID) -> ChannelPartner:
        partner = ChannelPartner(
            **payload.model_dump(),
            created_by_id=actor_id,
            updated_by_id=actor_id,
        )
        self.session.add(partner)
        await self.commit()
        await self.session.refresh(partner)
        return partner

    async def get_partner(self, partner_id: UUID) -> ChannelPartner:
        partner = (
            await self.session.execute(
                select(ChannelPartner).where(
                    ChannelPartner.id == partner_id, ChannelPartner.is_deleted.is_(False)
                )
            )
        ).scalar_one_or_none()
        if partner is None:
            raise NotFoundError("Channel partner not found.")
        return partner

    async def list_partners(self) -> list[ChannelPartner]:
        rows = await self.session.execute(
            select(ChannelPartner)
            .where(ChannelPartner.is_deleted.is_(False))
            .order_by(ChannelPartner.company_name)
        )
        return list(rows.scalars().all())

    async def update_partner(
        self, partner_id: UUID, payload: ChannelPartnerUpdate, *, actor_id: UUID
    ) -> ChannelPartner:
        partner = await self.get_partner(partner_id)
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(partner, key, value)
        partner.updated_by_id = actor_id
        await self.commit()
        await self.session.refresh(partner)
        return partner

    async def partner_for_user(self, user_id: UUID) -> ChannelPartner | None:
        """Resolve the ACTIVE ChannelPartner profile a broker login is attached
        to. A deactivated (is_active=False) or soft-deleted partner resolves to
        None, so the portal (submit/dashboard/leads/commissions) rejects them."""
        return (
            await self.session.execute(
                select(ChannelPartner).where(
                    ChannelPartner.user_id == user_id,
                    ChannelPartner.is_deleted.is_(False),
                    ChannelPartner.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()

    # --- stats -------------------------------------------------------------
    async def _lead_counts(self, partner_id: UUID | None = None) -> dict[UUID, dict[str, int]]:
        """{partner_id: {total, sold, lost}} over non-deleted attributed leads."""
        stmt = (
            select(
                Lead.partner_id,
                func.count().label("total"),
                func.count().filter(Lead.stage_code == SOLD).label("sold"),
                func.count().filter(Lead.stage_code == LOST).label("lost"),
            )
            .where(Lead.is_deleted.is_(False), Lead.partner_id.is_not(None))
            .group_by(Lead.partner_id)
        )
        if partner_id is not None:
            stmt = stmt.where(Lead.partner_id == partner_id)
        rows = await self.session.execute(stmt)
        return {r.partner_id: {"total": r.total, "sold": r.sold, "lost": r.lost} for r in rows}

    async def _payout_sums(self, partner_id: UUID | None = None) -> dict[UUID, dict[str, Decimal]]:
        """{partner_id: {paid, outstanding}} — outstanding = accrued (not paid/reversed)."""
        stmt = (
            select(
                BrokeragePayout.partner_id,
                func.coalesce(
                    func.sum(BrokeragePayout.amount).filter(BrokeragePayout.status == "paid"),
                    0,
                ).label("paid"),
                func.coalesce(
                    func.sum(BrokeragePayout.amount).filter(BrokeragePayout.status == "accrued"),
                    0,
                ).label("outstanding"),
            )
            .group_by(BrokeragePayout.partner_id)
        )
        if partner_id is not None:
            stmt = stmt.where(BrokeragePayout.partner_id == partner_id)
        rows = await self.session.execute(stmt)
        return {
            r.partner_id: {"paid": Decimal(r.paid), "outstanding": Decimal(r.outstanding)}
            for r in rows
        }

    @staticmethod
    def _stats_from(
        partner_id: UUID,
        lead_counts: dict[UUID, dict[str, int]],
        payout_sums: dict[UUID, dict[str, Decimal]],
    ) -> ChannelPartnerStats:
        lc = lead_counts.get(partner_id, {"total": 0, "sold": 0, "lost": 0})
        ps = payout_sums.get(partner_id, {"paid": Decimal("0"), "outstanding": Decimal("0")})
        total, sold, lost = lc["total"], lc["sold"], lc["lost"]
        paid, outstanding = ps["paid"], ps["outstanding"]
        return ChannelPartnerStats(
            leads_total=total,
            leads_active=max(0, total - sold - lost),
            leads_sold=sold,
            conversion_rate=(sold / total) if total else 0.0,
            brokerage_accrued=paid + outstanding,
            brokerage_paid=paid,
            brokerage_outstanding=outstanding,
        )

    async def roster_with_stats(self) -> list[tuple[ChannelPartner, ChannelPartnerStats]]:
        partners = await self.list_partners()
        lead_counts = await self._lead_counts()
        payout_sums = await self._payout_sums()
        return [(p, self._stats_from(p.id, lead_counts, payout_sums)) for p in partners]

    async def stats_for(self, partner_id: UUID) -> ChannelPartnerStats:
        lead_counts = await self._lead_counts(partner_id)
        payout_sums = await self._payout_sums(partner_id)
        return self._stats_from(partner_id, lead_counts, payout_sums)

    async def stage_breakdown(self, partner_id: UUID) -> list[PartnerStageCount]:
        rows = await self.session.execute(
            select(Lead.stage_code, func.count().label("count"))
            .where(
                Lead.is_deleted.is_(False),
                Lead.partner_id == partner_id,
            )
            .group_by(Lead.stage_code)
        )
        return [
            PartnerStageCount(stage_code=r.stage_code, label=_humanize(r.stage_code), count=r.count)
            for r in rows
        ]

    async def partner_leads(self, partner_id: UUID, *, eager: bool = False) -> list[Lead]:
        stmt = (
            select(Lead)
            .where(Lead.is_deleted.is_(False), Lead.partner_id == partner_id)
            .order_by(Lead.created_at.desc())
        )
        if eager:
            # Staff LeadRead needs customer/assigned_to/partner without lazy loads.
            stmt = stmt.options(
                selectinload(Lead.customer),
                selectinload(Lead.assigned_to),
                selectinload(Lead.partner),
            )
        rows = await self.session.execute(stmt)
        return list(rows.scalars().all())

    # --- payouts -----------------------------------------------------------
    async def list_payouts(self, partner_id: UUID | None = None) -> list[BrokeragePayout]:
        stmt = select(BrokeragePayout).order_by(BrokeragePayout.created_at.desc())
        if partner_id is not None:
            stmt = stmt.where(BrokeragePayout.partner_id == partner_id)
        rows = await self.session.execute(stmt)
        return list(rows.scalars().all())

    async def payouts_for_lead(self, lead_id: UUID) -> list[BrokeragePayout]:
        """Brokerage payout(s) accrued for a specific lead (Phase C4 lead tab)."""
        stmt = (
            select(BrokeragePayout)
            .where(BrokeragePayout.lead_id == lead_id)
            .order_by(BrokeragePayout.created_at.desc())
        )
        rows = await self.session.execute(stmt)
        return list(rows.scalars().all())

    async def get_payout(self, payout_id: UUID) -> BrokeragePayout:
        payout = await self.session.get(BrokeragePayout, payout_id)
        if payout is None:
            raise NotFoundError("Brokerage payout not found.")
        return payout

    async def update_payout(
        self, payout_id: UUID, *, status: str, paid_on=None, note: str | None = None
    ) -> BrokeragePayout:
        payout = await self.get_payout(payout_id)
        payout.status = status
        if paid_on is not None:
            payout.paid_on = paid_on
        if note is not None:
            payout.note = note
        await self.commit()
        await self.session.refresh(payout)
        return payout

    # --- lead submission (broker portal) -----------------------------------
    async def submit_partner_lead(
        self, partner: ChannelPartner, payload: PartnerLeadSubmit, *, actor_id: UUID
    ) -> Lead:
        """A logged-in broker refers a lead. Industry, source and partner
        attribution are forced here — never taken from the client."""
        lead_payload = LeadCreate(
            industry=LeadIndustry.real_estate,
            title=payload.title or payload.contact_name,
            contact_name=payload.contact_name,
            contact_email=payload.contact_email,
            contact_phone=payload.contact_phone,
            source="partner_referral",
            partner_id=partner.id,
            interest=payload.interest,
            property_type=payload.property_type,
            preferred_location=payload.preferred_location,
            budget_min=payload.budget_min,
            budget_max=payload.budget_max,
            notes=payload.notes,
        )
        lead = await LeadService(self.session).create_lead(
            lead_payload, actor_id=actor_id, actor_business_type=LeadIndustry.real_estate
        )
        # Alert managers/owners — a partner referral lands unassigned and needs
        # triage. Best-effort email (no-op if email unconfigured).
        await self._alert_managers_of_referral(partner, payload)
        return lead

    async def _alert_managers_of_referral(self, partner: ChannelPartner, payload: PartnerLeadSubmit) -> None:
        org_id = current_org(self.session)
        if org_id is None:
            return
        emails = (
            await self.session.execute(
                select(User.email).where(
                    User.organization_id == org_id,
                    User.role.in_([UserRole.sales_manager, UserRole.owner]),
                    User.status == UserStatus.active,
                )
            )
        ).scalars().all()
        emails = [e for e in emails if e]
        if not emails:
            return
        requirement = " · ".join(x for x in [payload.property_type, payload.preferred_location] if x) or None
        await EmailService().send_partner_referral_alert(
            emails, partner=partner.company_name, contact_name=payload.contact_name, requirement=requirement
        )

    # --- brokerage accrual (called from the Sold transition) ---------------
    async def accrue_brokerage(self, lead: Lead, *, sales_order) -> BrokeragePayout | None:
        """Accrue a partner's brokerage when a referred lead is Sold. Idempotent:
        one payout per lead. Returns the payout, or None if not applicable."""
        if lead.partner_id is None:
            return None
        partner = (
            await self.session.execute(
                select(ChannelPartner).where(ChannelPartner.id == lead.partner_id)
            )
        ).scalar_one_or_none()
        if partner is None or not partner.is_active:
            return None
        # Don't double-accrue if a LIVE payout already exists for this lead. A
        # `reversed` payout (deal refunded / reopened) does NOT block a genuine
        # re-accrual on a later re-sold transition.
        existing = (
            await self.session.execute(
                select(BrokeragePayout.id).where(
                    BrokeragePayout.lead_id == lead.id,
                    BrokeragePayout.status != "reversed",
                )
            )
        ).first()
        if existing is not None:
            return None

        deal_value = Decimal(str(getattr(sales_order, "deal_value", 0) or 0))
        if deal_value <= 0:
            # Real-estate leads keep their expected size in budget_* — the `value`
            # column is hidden on the form and stays 0, which would make every
            # percent brokerage accrue 0. Fall back to the budget as the deal size.
            deal_value = Decimal(str(lead.budget_max or lead.budget_min or 0))
        rate = Decimal(str(partner.brokerage_rate or 0))
        if partner.brokerage_type == "flat":
            amount = rate
        else:  # percent
            amount = (deal_value * rate / Decimal(100)).quantize(Decimal("0.01"))
        if amount <= 0:
            return None

        payout = BrokeragePayout(
            partner_id=partner.id,
            lead_id=lead.id,
            sales_order_id=getattr(sales_order, "id", None),
            deal_value=deal_value,
            rate_type=partner.brokerage_type,
            rate_snapshot=rate,
            amount=amount,
            status="accrued",
            note=f"Auto-accrued on Sold ({partner.brokerage_type} {rate}).",
        )
        self.session.add(payout)
        # Caller (stage transition) owns the commit.
        return payout

    async def _reverse_accrued(self, *, lead_id=None, sales_order_id=None, why: str) -> int:
        """Flip still-accrued brokerage payouts to `reversed` when the underlying
        deal is undone (refund / reopen). Only 'accrued' rows are touched — a
        payout already 'paid' out is a real disbursement handled manually, never
        auto-clawed-back. The caller owns the commit."""
        if lead_id is None and sales_order_id is None:
            return 0
        stmt = select(BrokeragePayout).where(BrokeragePayout.status == "accrued")
        if lead_id is not None:
            stmt = stmt.where(BrokeragePayout.lead_id == lead_id)
        if sales_order_id is not None:
            stmt = stmt.where(BrokeragePayout.sales_order_id == sales_order_id)
        rows = (await self.session.execute(stmt)).scalars().all()
        for p in rows:
            p.status = "reversed"
            p.note = f"{p.note or ''} | reversed ({why})".strip(" |")
        return len(rows)

    async def reverse_brokerage_for_lead(self, lead_id, *, why: str) -> int:
        return await self._reverse_accrued(lead_id=lead_id, why=why)

    async def reverse_brokerage_for_sales_order(self, sales_order_id, *, why: str) -> int:
        return await self._reverse_accrued(sales_order_id=sales_order_id, why=why)
