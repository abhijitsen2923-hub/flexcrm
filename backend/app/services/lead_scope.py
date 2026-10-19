"""Which leads a user may see — a custom role's "Data access": chosen campaigns, chosen sources, and/or only the leads
assigned to them.

One rule, applied centrally. For a request made by a user whose custom role limits leads, every ORM SELECT / UPDATE /
DELETE that touches a lead — or a record built from one — gets the user's lead filter, added by a do_orm_execute
listener (with_loader_criteria). Lists, counts, searches, dashboard / analytics figures, exports, duplicate checks and
lookups by id all respect it without each endpoint remembering to. Jobs, webhooks and the portals never set a scope,
so they work exactly as before.

Records built from a lead follow it:
- customer — visible when created from a visible lead, or linked to one;
- booking, sales order — visible when their lead is (one with no lead: when its customer is);
- site visit, channel-partner brokerage — visible when their lead is;
- a booking's payment plan, receipts, refunds, invoices and KYC documents; a sales order's invoices, their payments
  and the commissions accrued on it — visible when the booking / order is;
- a customer's deals, activities and finance contracts (with their demands and receipts) — when the customer is.

What the listener can't see is checked by hand:
- rows read by lead id without loading the lead (stage / owner / intent history, call logs …) — the endpoint first
  loads the lead (`_enforce_lead_access`), which the filter already turns into a 404;
- phone-matched calls (Callyzer) — the Calls list adds `lead_terms` over the leads table itself;
- statements that must see EVERY row (the next lead / customer / order number, campaign renames and merges rewriting
  lead rows) run with `.execution_options(**SKIP_LEAD_SCOPE)` (app/core/tenancy.py) or inside `unscoped()`.

Front-line rep roles (sales_executive, telecaller) keep their existing per-endpoint "own leads only" rule — nothing
here changes for them, nor for owners, managers and the other built-in roles.
"""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator
from uuid import UUID

from sqlalchemy import and_, event, false, func, or_, select, union
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria

from app.core.campaign_names import campaign_key
from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.core.tenancy import SKIP_LEAD_SCOPE_OPTION
from app.database.enums import UserRole
from app.models.campaign import Campaign, CampaignAlias
from app.models.custom_role import UserCustomRoleAssignment
from app.models.customer import Customer
from app.models.lead import Lead

_INFO_KEY = "lead_scope"
_PAUSED_KEY = "lead_scope_paused"


def source_key(value: object) -> str:
    """How a lead source is compared: case and surrounding spaces ignored ("facebook / meta" = "Facebook / Meta")."""
    return str(value or "").strip().lower()


def _stored_keys(value: str) -> set[str]:
    """Keys a stored campaign spelling can have in SQL (lower(trim(x)) keeps inner spaces) and in Python
    (campaign_key collapses them)."""
    return {k for k in (value.strip().lower(), campaign_key(value)) if k}


@dataclass(frozen=True)
class LeadScope:
    """A user's lead limits. Each dimension is None when it isn't limited; a lead must pass every limit that is set."""

    owner_id: UUID | None = None
    # Keys of every allowed campaign's name and its older spellings (aliases).
    campaign_keys: frozenset[str] | None = None
    source_keys: frozenset[str] | None = None
    # For the screens: the allowed campaigns' current names and the allowed source labels.
    campaign_names: tuple[str, ...] = field(default=())
    sources: tuple[str, ...] = field(default=())

    @property
    def limited(self) -> bool:
        return self.owner_id is not None or self.campaign_keys is not None or self.source_keys is not None

    def lead_terms(self, cols):
        """The condition a visible lead meets, over `cols` — the Lead entity (ORM) or `Lead.__table__.c` (Core).
        A lead with no campaign (or no source) fails a campaign (or source) limit: lower(trim(NULL)) is NULL, never
        IN the list."""
        terms = []
        if self.owner_id is not None:
            terms.append(cols.assigned_to_id == self.owner_id)
        if self.campaign_keys is not None:
            terms.append(
                func.lower(func.trim(cols.campaign)).in_(sorted(self.campaign_keys)) if self.campaign_keys else false()
            )
        if self.source_keys is not None:
            terms.append(func.lower(func.trim(cols.source)).in_(sorted(self.source_keys)) if self.source_keys else false())
        return and_(*terms)

    def allows(self, *, campaign: str | None, source: str | None) -> bool:
        """Whether a lead with this campaign and source is inside the limits (the write-side check). The owner limit
        isn't checked here — who a lead is handed to is the assign rules' business."""
        if self.campaign_keys is not None and (not campaign or campaign_key(campaign) not in self.campaign_keys):
            return False
        if self.source_keys is not None and (not source or source_key(source) not in self.source_keys):
            return False
        return True

    def refusal(self, *, campaign: str | None, source: str | None) -> str | None:
        """Why a lead with these values is outside the limits ("Not your campaign …"), or None."""
        if self.campaign_keys is not None and (not campaign or campaign_key(campaign) not in self.campaign_keys):
            allowed = ", ".join(self.campaign_names) or "none"
            if not campaign:
                return f"Choose a campaign — your access covers only: {allowed}."
            return f"Not your campaign ({campaign.strip()}) — your access covers only: {allowed}."
        if self.source_keys is not None and (not source or source_key(source) not in self.source_keys):
            allowed = ", ".join(self.sources) or "none"
            if not source:
                return f"Choose a source — your access covers only: {allowed}."
            return f"Not your source ({source.strip()}) — your access covers only: {allowed}."
        return None

    def fingerprint(self) -> str:
        """Short, stable id of these limits — part of dashboard / analytics cache keys, so a limited user never
        shares cached figures with anyone who sees more (or different) leads."""
        parts = [
            str(self.owner_id or ""),
            ",".join(sorted(self.campaign_keys)) if self.campaign_keys is not None else "*",
            ",".join(sorted(self.source_keys)) if self.source_keys is not None else "*",
        ]
        return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _uuids(values) -> list[UUID]:
    out: list[UUID] = []
    for value in values or []:
        try:
            out.append(UUID(str(value)))
        except (TypeError, ValueError):
            continue
    return out


def role_limits_leads(role) -> bool:
    """Whether a custom role limits which leads its users see."""
    return role is not None and (
        bool(role.lead_own_only) or role.lead_campaign_ids is not None or role.lead_sources is not None
    )


async def scope_for_role(session: AsyncSession, role, *, user_id: UUID | None) -> LeadScope | None:
    """The LeadScope a custom role's settings give (None = sees every lead)."""
    if not role_limits_leads(role):
        return None
    own_only = bool(role.lead_own_only)
    campaign_ids = role.lead_campaign_ids
    sources = role.lead_sources

    campaign_keys: frozenset[str] | None = None
    campaign_names: tuple[str, ...] = ()
    if campaign_ids is not None:
        ids = _uuids(campaign_ids)
        names: list[str] = []
        aliases: list[str] = []
        if ids:
            names = list((await session.execute(select(Campaign.name).where(Campaign.id.in_(ids)))).scalars())
            aliases = list(
                (await session.execute(select(CampaignAlias.alias).where(CampaignAlias.campaign_id.in_(ids)))).scalars()
            )
        # A campaign that no longer exists adds nothing — the role then sees less, never more.
        campaign_keys = frozenset(k for value in [*names, *aliases] if value for k in _stored_keys(value))
        campaign_names = tuple(sorted(names, key=str.lower))

    source_keys: frozenset[str] | None = None
    source_labels: tuple[str, ...] = ()
    if sources is not None:
        cleaned = [str(s).strip() for s in sources if str(s or "").strip()]
        source_keys = frozenset(source_key(s) for s in cleaned)
        source_labels = tuple(cleaned)

    return LeadScope(
        owner_id=user_id if own_only else None,
        campaign_keys=campaign_keys,
        source_keys=source_keys,
        campaign_names=campaign_names,
        sources=source_labels,
    )


async def load_lead_scope(session: AsyncSession, user) -> LeadScope | None:
    """The user's lead limits from their custom role (None = every lead their permissions allow).

    Applied even while the role is switched off: a switched-off role grants nothing, and whatever its user still
    holds (individual grants) stays inside the role's limits — never more."""
    if user is None or getattr(user, "role", None) != UserRole.custom:
        return None
    assignment = (
        await session.execute(select(UserCustomRoleAssignment).where(UserCustomRoleAssignment.user_id == user.id))
    ).scalar_one_or_none()
    role = assignment.custom_role if assignment else None
    return await scope_for_role(session, role, user_id=user.id)


async def user_can_see_lead(session: AsyncSession, user_id: UUID, lead) -> bool:
    """Whether a user (not necessarily the request's) may see this lead — for messages about it, e.g. @mentions."""
    from app.models.user import User  # local: keeps this module's imports to the tenant models

    role_name = await session.scalar(select(User.role).where(User.id == user_id))
    if role_name != UserRole.custom:
        return True
    assignment = (
        await session.execute(select(UserCustomRoleAssignment).where(UserCustomRoleAssignment.user_id == user_id))
    ).scalar_one_or_none()
    scope = await scope_for_role(session, assignment.custom_role if assignment else None, user_id=user_id)
    if scope is None:
        return True
    if scope.owner_id is not None and lead.assigned_to_id != scope.owner_id:
        return False
    return scope.allows(campaign=lead.campaign, source=lead.source)


def set_request_scope(session: AsyncSession, scope: LeadScope | None) -> None:
    """Turn the central filter on for the rest of this request's session (or off, with None)."""
    if scope is not None and scope.limited:
        session.info[_INFO_KEY] = scope
    else:
        session.info.pop(_INFO_KEY, None)


def request_scope(session: AsyncSession) -> LeadScope | None:
    """The limits of the user this request runs for (None = no limits)."""
    return session.info.get(_INFO_KEY)


async def check_new_link(
    session: AsyncSession, *, lead_id: UUID | None, customer_id: UUID | None, what: str, customer_ok: bool = True
) -> None:
    """Before a limited user saves a record built from a lead (site visit, booking, contract …): it must point at a
    lead (or, where `customer_ok`, a customer) they can see — else it would vanish from their view the moment it's
    saved, or attach to someone they can't see. No-op for users without limits."""
    if request_scope(session) is None:
        return
    if lead_id is not None:
        if await session.scalar(select(Lead.id).where(Lead.id == lead_id)) is None:
            raise NotFoundError("Lead not found.")
        return
    if customer_ok and customer_id is not None:
        if await session.scalar(select(Customer.id).where(Customer.id == customer_id)) is None:
            raise NotFoundError("Customer not found.")
        return
    raise ValidationError(f"Choose the lead for this {what} — your access covers only some leads.")


def refuse_if_limited(session: AsyncSession, what: str) -> None:
    """For actions that work on every lead / booking at once (e.g. marking a project milestone, recomputing
    scorecards): a user limited to some leads can't run them — they'd act on, or report on, rows they can't see."""
    if request_scope(session) is not None:
        raise AuthorizationError(f"{what} covers every lead, and your access is limited to some — ask a manager.")


@contextmanager
def unscoped(session: AsyncSession) -> Iterator[None]:
    """Run a block that must see every row (e.g. re-reading a lead the user just handed to someone else, to answer
    the request) — never to list or search anything for the user."""
    previous = session.info.get(_PAUSED_KEY, False)
    session.info[_PAUSED_KEY] = True
    try:
        yield
    finally:
        session.info[_PAUSED_KEY] = previous


# --- the central filter -------------------------------------------------------------------------------------------
# The subqueries below select from the TABLES (Core), not the mapped classes, so the listener's own criteria are never
# re-applied inside them.


def _visible_lead_ids(scope: LeadScope):
    leads = Lead.__table__.c
    return select(leads.id).where(scope.lead_terms(leads))


def _visible_customer_ids(scope: LeadScope):
    leads = Lead.__table__.c
    customers = Customer.__table__.c
    return union(
        select(leads.customer_id).where(leads.customer_id.is_not(None), scope.lead_terms(leads)),
        select(customers.id).where(customers.source_lead_id.in_(_visible_lead_ids(scope))),
    )


def _lead_or_customer(entity, scope: LeadScope):
    """A record with a lead follows the lead; one without follows its customer."""
    return or_(
        entity.lead_id.in_(_visible_lead_ids(scope)),
        and_(entity.lead_id.is_(None), entity.customer_id.in_(_visible_customer_ids(scope))),
    )


_LISTENER_REGISTERED = False


def register_lead_scope_listener() -> None:
    """Add the request user's lead filter to every ORM statement of a limited user's request. Idempotent."""
    global _LISTENER_REGISTERED
    if _LISTENER_REGISTERED:
        return
    _LISTENER_REGISTERED = True

    # Imported here: these modules pull in much of the app, and only the listener needs them.
    from app.finance.models import (
        CommissionLedger,
        CustomerContract,
        CustomerDemand,
        DemandReceipt,
        Invoice,
        Payment,
        SalesOrder,
    )
    from app.models.activity import Activity
    from app.models.channel_partner import BrokeragePayout
    from app.models.deal import Deal
    from app.real_estate.models import (
        Booking,
        BookingInvoice,
        BookingKycDoc,
        BookingRefund,
        PaymentReceipt,
        PaymentSchedule,
        SiteVisit,
    )

    def _criteria(scope: LeadScope) -> list:
        bookings = Booking.__table__.c
        orders = SalesOrder.__table__.c
        invoices = Invoice.__table__.c
        visible_bookings = select(bookings.id).where(_lead_or_customer(bookings, scope))
        visible_orders = select(orders.id).where(_lead_or_customer(orders, scope))
        visible_invoices = select(invoices.id).where(invoices.sales_order_id.in_(visible_orders))
        contracts = CustomerContract.__table__.c
        demands = CustomerDemand.__table__.c
        visible_contracts = select(contracts.id).where(contracts.customer_id.in_(_visible_customer_ids(scope)))
        visible_demands = select(demands.id).where(demands.contract_id.in_(visible_contracts))
        return [
            with_loader_criteria(Lead, scope.lead_terms(Lead), include_aliases=True),
            with_loader_criteria(
                Customer,
                or_(
                    Customer.source_lead_id.in_(_visible_lead_ids(scope)),
                    Customer.id.in_(_visible_customer_ids(scope)),
                ),
                include_aliases=True,
            ),
            with_loader_criteria(Booking, _lead_or_customer(Booking, scope), include_aliases=True),
            with_loader_criteria(SiteVisit, SiteVisit.lead_id.in_(_visible_lead_ids(scope)), include_aliases=True),
            with_loader_criteria(SalesOrder, _lead_or_customer(SalesOrder, scope), include_aliases=True),
            with_loader_criteria(Invoice, Invoice.sales_order_id.in_(visible_orders), include_aliases=True),
            with_loader_criteria(Payment, Payment.invoice_id.in_(visible_invoices), include_aliases=True),
            *(
                with_loader_criteria(model, model.booking_id.in_(visible_bookings), include_aliases=True)
                for model in (PaymentSchedule, PaymentReceipt, BookingRefund, BookingInvoice, BookingKycDoc)
            ),
            with_loader_criteria(
                CommissionLedger, CommissionLedger.sales_order_id.in_(visible_orders), include_aliases=True
            ),
            with_loader_criteria(
                BrokeragePayout, BrokeragePayout.lead_id.in_(_visible_lead_ids(scope)), include_aliases=True
            ),
            *(
                with_loader_criteria(model, model.customer_id.in_(_visible_customer_ids(scope)), include_aliases=True)
                for model in (Deal, Activity, CustomerContract)
            ),
            with_loader_criteria(CustomerDemand, CustomerDemand.contract_id.in_(visible_contracts), include_aliases=True),
            with_loader_criteria(DemandReceipt, DemandReceipt.demand_id.in_(visible_demands), include_aliases=True),
        ]

    @event.listens_for(Session, "do_orm_execute")
    def _apply_lead_scope(state: ORMExecuteState) -> None:
        scope: LeadScope | None = state.session.info.get(_INFO_KEY)
        if scope is None or state.session.info.get(_PAUSED_KEY):
            return
        if state.execution_options.get(SKIP_LEAD_SCOPE_OPTION):
            return
        if not (state.is_select or state.is_update or state.is_delete):
            return
        # Refreshing attributes of an object this request already loaded (it was visible then) — filtering here could
        # only turn a harmless refresh into "object deleted".
        if state.is_column_load:
            return
        state.statement = state.statement.options(*_criteria(scope))

