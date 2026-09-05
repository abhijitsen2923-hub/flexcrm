from datetime import UTC, datetime
from uuid import UUID

from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.core.permissions import STAGE_MANAGER_ROLES, can_set_stage
from app.core.tenancy import current_org
from app.database.enums import LeadIndustry, PipelineStageCategory, UnitStatus, UserRole
from app.models.lead import Lead
from app.models.pipeline_stage import PipelineStage  # noqa: F401  (kept for type hinting context)
from app.models.stage_transition import StageTransition
from app.repositories.leads import LeadRepository
from app.repositories.pipeline_stages import PipelineStageRepository
from app.repositories.stage_transitions import StageTransitionRepository
from app.repositories.users import UserRepository
from app.schemas.stage_transition import MIN_COMMENT_LENGTH, StageTransitionCreate
from app.services.base import ServiceBase
from app.services.customer_promotion import CustomerPromotionService
from app.services.lead_documents import LeadDocumentService
from app.services.notifications import NotificationService
from app.services.realtime import realtime_manager
# Phase 4 wiring — auto-create SalesOrder + Invoice + Commission accrual on
# Sold. Imported lazily inside the method to avoid the circular import that
# would otherwise happen when `app.finance.models` registers with metadata.
from app.finance.services import SalesOrderService

logger = get_logger(__name__)


# The "Sold" stage shares the same `code` slug across both industries
# (Education position 12 and Travel position 12). One constant covers both.
SOLD_STAGE_CODE = "sold"

# Real-estate "Booked / Token" (position 7) — the lead's first payment. Moving
# here captures the property/token on a Booking and promotes the lead to a
# Customer ("any payment ⇒ customer"), rather than waiting for Sold.
BOOKED_STAGE_CODE = "booked"

# Travel-only gate: cannot leave this stage until all required docs are uploaded.
TRAVEL_DOCS_PENDING_STAGE = "visa_documentation_pending"

# Closed-lost stages — any move out of these is a "reopen" and skips the
# normal backward-only-by-manager rule.
CLOSED_LOST_STAGE_CODES = {"did_not_pick", "not_interested", "disqualified"}

# Stages a BULK move must NOT target: each needs per-lead capture (a booking/token
# on "booked", a site-visit slot on "site_visit_confirmed") or fires heavy, near-
# irreversible side effects ("sold" → Customer + SalesOrder + Invoice + commission +
# brokerage). Those must be moved one lead at a time.
BULK_BLOCKED_STAGE_CODES = {SOLD_STAGE_CODE, BOOKED_STAGE_CODE, "site_visit_confirmed"}


class StageTransitionService(ServiceBase):
    """Owns every Lead stage move (spec §3.2).

    A transition is the ONLY supported path to changing `Lead.stage_code` — the
    `PATCH /leads/{id}` endpoint explicitly rejects `stage_code` updates and
    redirects callers here.
    """

    def __init__(self, session):
        super().__init__(session)
        self.lead_repository = LeadRepository(session)
        self.stage_repository = PipelineStageRepository(session)
        self.transition_repository = StageTransitionRepository(session)
        self.notification_service = NotificationService(session)
        self.promotion_service = CustomerPromotionService(session)
        self.document_service = LeadDocumentService(session)
        self.user_repository = UserRepository(session)

    async def list_transitions(self, lead_id: UUID) -> list[StageTransition]:
        lead = await self.lead_repository.get(lead_id)
        if lead is None:
            raise NotFoundError("Lead not found.")
        return await self.transition_repository.for_lead(lead_id)

    async def create_transition(
        self,
        lead_id: UUID,
        payload: StageTransitionCreate,
        *,
        actor_id: UUID,
        actor_role: UserRole,
    ) -> StageTransition:
        lead = await self.lead_repository.get(lead_id, options=self.lead_repository.default_options)
        if lead is None:
            raise NotFoundError("Lead not found.")

        target_stage = await self.stage_repository.find(lead.industry, payload.to_stage_code)
        if target_stage is None:
            raise ValidationError(
                f"Stage '{payload.to_stage_code}' is not valid for industry '{lead.industry.value}'."
            )

        current_stage = await self.stage_repository.find(lead.industry, lead.stage_code)
        if current_stage is None:
            # Shouldn't happen — composite FK enforces this — but fail loudly if it does.
            raise ValidationError(f"Lead's current stage '{lead.stage_code}' is unknown.")

        # Spec §3.2: mandatory comment, ≥10 chars. Pydantic already enforced
        # this; the floor lives in `MIN_COMMENT_LENGTH` for any non-schema caller.
        if len(payload.comment.strip()) < MIN_COMMENT_LENGTH:
            raise ValidationError(
                f"Comment must be at least {MIN_COMMENT_LENGTH} characters."
            )

        # Reopen-lost-leads (spec Open Q #6): moving OUT of a closed-lost stage
        # is always allowed and treated as a fresh re-entry into the funnel.
        # The transition row keeps a real `from_stage_code` so the history
        # records the reopen explicitly.
        is_reopen = lead.stage_code in CLOSED_LOST_STAGE_CODES and target_stage.category == PipelineStageCategory.active

        # Role-based access to stages (real-estate lifecycle v2). A restricted
        # role can only move a lead to the stages its role allows (e.g. a
        # telecaller can't set `booked`; only managers can `sold`). Unrestricted
        # roles pass. Reopen flows still honour this (you can only reopen into a
        # stage your role can set).
        if not can_set_stage(actor_role, target_stage.code):
            raise AuthorizationError(
                f"Your role is not allowed to move a lead to '{target_stage.name}'."
            )

        # Backward moves (to an earlier active stage) are manager-only. Reopen
        # flows (out of a closed-lost stage) skip this. Fixed to use the real
        # manager roles — the old {admin, manager} set is legacy and unassignable,
        # so backward moves were silently blocked for every real user.
        if (
            not is_reopen
            and target_stage.position < current_stage.position
            and target_stage.category == PipelineStageCategory.active
            and actor_role not in STAGE_MANAGER_ROLES
        ):
            raise AuthorizationError("Only managers can move a lead backward in the pipeline.")

        # Travel-only gate: if leaving `visa_documentation_pending`, every
        # required document must be uploaded first.
        if (
            current_stage.code == TRAVEL_DOCS_PENDING_STAGE
            and target_stage.code != TRAVEL_DOCS_PENDING_STAGE
        ):
            await self.document_service.assert_checklist_complete(lead)

        # Auto-seed the doc checklist when ENTERING visa_documentation_pending
        # so the UI has rows to populate.
        if target_stage.code == TRAVEL_DOCS_PENDING_STAGE:
            await self.document_service.ensure_checklist(lead)

        # Education-only field: capture batch_code on the Sold transition so
        # the auto-Customer can record which cohort the student joined.
        if (
            target_stage.code == SOLD_STAGE_CODE
            and lead.industry == LeadIndustry.education
            and payload.batch_code
        ):
            lead.batch_code = payload.batch_code.strip()[:64]

        transition = await self.transition_repository.create(
            {
                "lead_id": lead.id,
                "from_stage_code": lead.stage_code,
                "to_stage_code": target_stage.code,
                "comment": payload.comment.strip(),
                "next_action_date": payload.next_action_date,
                "attachment_path": payload.attachment_path,
                "performed_by_id": actor_id,
                "mentions": [str(uid) for uid in (payload.mentions or [])] or None,
            }
        )

        # Update the lead's stage and the denormalized snapshots. next_action_date
        # mirrors the LATEST transition's value (may be None → clears a prior action),
        # keeping the leads-list "due" filter in lock-step with the reminders job.
        lead.stage_code = target_stage.code
        lead.last_comment_preview = payload.comment.strip()[:255]
        lead.last_comment_at = datetime.now(UTC)
        lead.next_action_date = payload.next_action_date
        lead.stage_changed_at = datetime.now(UTC)
        lead.updated_by_id = actor_id

        # @mentions create in-app notifications. Spec §3.2 also calls out next-action
        # date → task creation; that wiring lives in the Tasks service so it stays
        # decoupled here.
        for mentioned_id in payload.mentions or []:
            await self.notification_service.create_notification(
                user_id=mentioned_id,
                message=(
                    f"You were mentioned on lead #{lead.lead_number} "
                    f"({lead.title}) — {payload.comment.strip()[:120]}"
                ),
            )

        # Real-estate "Booked / Token" (position 7): the lead's first payment.
        # Only promote when a token/booking is actually recorded (the payment) —
        # matching "any payment ⇒ customer"; a booking-less move to `booked` (e.g.
        # a backward correction) must NOT create a customer or re-onboard one.
        # Promotion is idempotent, so a later Sold transition still works.
        held_unit_event: tuple[str, str] | None = None
        if (
            target_stage.code == BOOKED_STAGE_CODE
            and lead.industry == LeadIndustry.real_estate
            and payload.booking is not None
        ):
            # Salesperson: an explicit pick wins; else keep the lead's owner; else
            # fall back to the user recording the booking — so the promoted
            # customer always has an owner even for roles that can't pick a user.
            if payload.assigned_to_id is not None:
                # Org-scoped: the explicit salesperson pick must be a user in this
                # tenant — `users` is shared, so an unscoped id could point at
                # another org's user (cross-tenant IDOR guard).
                assignee = await self.user_repository.get_in_org(
                    payload.assigned_to_id, current_org(self.session)
                )
                if assignee is None:
                    raise NotFoundError("Assigned user not found.")
                lead.assigned_to_id = payload.assigned_to_id
            elif lead.assigned_to_id is None:
                lead.assigned_to_id = actor_id
            # Channel-partner attribution + incentive exemption travel with the
            # booked move, independent of the salesperson. A CP pick sets partner_id
            # (only when provided, so it never silently clears one set on the lead
            # form); incentive_exempt marks an "Others / owner's reference" sale so
            # NOBODY accrues at Sold. FK is same-schema, so no cross-tenant guard.
            if payload.partner_id is not None:
                lead.partner_id = payload.partner_id
            lead.incentive_exempt = bool(payload.incentive_exempt)
            booking, held_unit_event = await self._apply_booked_token(lead, payload.booking)
            customer = await self.promotion_service.promote_from_lead(lead, actor_id=actor_id)
            if booking.customer_id is None:
                booking.customer_id = customer.id

        # Auto-promote on Sold (Education stage 12, Travel stage 12 — both
        # share code "sold"). Idempotent: a lead already linked to a Customer
        # just gets its status flipped to `active`.
        if target_stage.code == SOLD_STAGE_CODE:
            await self.promotion_service.promote_from_lead(lead, actor_id=actor_id)
            # Phase 4 — materialize the SalesOrder + Invoice + commission
            # accrual. Idempotent on lead_id (a re-sold transition won't
            # create a duplicate if one exists; the service skips creation
            # if a SalesOrder already references this lead).
            sales_service = SalesOrderService(self.session)
            from sqlalchemy import select as _select
            from app.finance.models import SalesOrder as _SalesOrder

            existing = (
                await self.session.execute(
                    _select(_SalesOrder).where(_SalesOrder.lead_id == lead.id)
                )
            ).scalar_one_or_none()
            order = existing
            if existing is None:
                order = await sales_service.create_from_lead(lead, actor_id=actor_id)
            # Channel-partner brokerage: accrue the referring partner's payout on
            # the Sold deal. Idempotent (one payout per lead) so a re-sold
            # transition with an existing order won't double-accrue. Skipped for an
            # incentive-exempt (owner's-reference) sale. Local import to avoid a
            # circular import at module load.
            if order is not None and not lead.incentive_exempt:
                from app.services.channel_partners import ChannelPartnerService

                await ChannelPartnerService(self.session).accrue_brokerage(lead, sales_order=order)
        elif current_stage.code == SOLD_STAGE_CODE:
            # Leaving Sold (reopened to an active stage, or moved to lost) undoes
            # the deal — reverse any still-accrued brokerage so it isn't left
            # payable on a collapsed sale.
            from app.services.channel_partners import ChannelPartnerService

            await ChannelPartnerService(self.session).reverse_brokerage_for_lead(
                lead.id, why=f"lead moved {SOLD_STAGE_CODE} -> {target_stage.code}"
            )

        await self.commit()
        await self.invalidate_reporting_cache()

        await realtime_manager.broadcast(
            {
                "event": "lead.stage_changed",
                "payload": {
                    "lead_id": str(lead.id),
                    "industry": lead.industry.value,
                    "from_stage_code": transition.from_stage_code,
                    "to_stage_code": transition.to_stage_code,
                    "by_user_id": str(actor_id),
                },
            }
        )
        # A "Booked / Token" move that put a unit on hold → tell inventory views so
        # the held unit leaves the available picker without a manual refresh.
        if held_unit_event is not None:
            await realtime_manager.broadcast(
                {
                    "event": "unit.status_changed",
                    "unit_id": held_unit_event[0],
                    "status": UnitStatus.hold.value,
                    "project_id": held_unit_event[1],
                }
            )
        return transition

    async def bulk_transition(
        self,
        lead_ids: list[UUID],
        to_stage_code: str,
        comment: str,
        *,
        actor_id: UUID,
        actor_role: UserRole,
        next_action_date: datetime | None = None,
        enforce_owner_id: UUID | None = None,
    ) -> dict:
        """Move each lead to `to_stage_code` via the normal single-lead path, so
        every rule and side effect (comment, role/backward gates, Sold/Booked
        promotions, realtime, history) applies identically. Per-lead failures are
        collected — one rejected lead (e.g. a backward move a rep can't make, or a
        stage that doesn't exist for that lead's industry) never aborts the rest.
        `enforce_owner_id`, when set (front-line reps), restricts moves to the
        caller's own leads — the same anti-poaching scope as the single endpoint.
        Returns {updated, failed, errors}."""
        # Capture/terminal stages are not bulk-movable — they need per-lead detail or
        # fire heavy side effects. Reject the whole request (the UI hides them too).
        if to_stage_code in BULK_BLOCKED_STAGE_CODES:
            raise ValidationError(
                "That stage can't be set in bulk — move those leads one at a time so "
                "each lead's booking, sale, or visit details are captured."
            )
        updated = 0
        errors: list[str] = []
        for lead_id in lead_ids:
            try:
                if enforce_owner_id is not None:
                    owned = await self.lead_repository.get(lead_id)
                    if owned is None or owned.assigned_to_id != enforce_owner_id:
                        errors.append("Some leads are not assigned to you and were skipped.")
                        continue
                await self.create_transition(
                    lead_id,
                    StageTransitionCreate(
                        to_stage_code=to_stage_code,
                        comment=comment,
                        next_action_date=next_action_date,
                    ),
                    actor_id=actor_id,
                    actor_role=actor_role,
                )
                updated += 1
            except (ValidationError, AuthorizationError, NotFoundError) as exc:
                # create_transition may have added rows before raising — clear them
                # so the session is clean for the next lead. Already-committed leads
                # (per-lead commit) are unaffected.
                await self.session.rollback()
                errors.append(exc.detail)
            except Exception:  # noqa: BLE001 — one bad lead must not abort the whole batch
                await self.session.rollback()
                logger.warning("bulk_transition: unexpected error on lead %s", lead_id, exc_info=True)
                errors.append("An unexpected error prevented moving some leads.")
        # Dedupe + cap the reasons for a compact toast; `failed` keeps the true count.
        seen: list[str] = []
        for e in errors:
            if e not in seen:
                seen.append(e)
        return {"updated": updated, "failed": len(errors), "errors": seen[:5]}

    async def _apply_booked_token(self, lead: Lead, capture):
        """Record the "Booked / Token" property + token on a Booking for the lead.

        Reuses the lead's existing non-cancelled Booking if one exists (e.g. one
        started in the Booking wizard) so we don't create a duplicate; otherwise
        creates a fresh draft Booking for the picked unit. The token puts the unit
        on HOLD (a reservation) — NOT `booked`: the booking stays a draft the user
        completes in the wizard, and step-4 confirm is what flips a held unit to
        `booked` + a confirmed booking. Holding keeps the unit out of the available
        picker (no double-book) while preserving the confirm → register path.
        Raises (rolling back the whole transition) if a new unit isn't available.
        Returns the Booking. Local imports avoid a circular import at module load
        (real_estate models register with the same metadata)."""
        from sqlalchemy import select as _select

        from app.database.enums import BookingStatus
        from app.real_estate.models import Booking, Unit

        existing = (
            await self.session.execute(
                _select(Booking)
                .where(Booking.lead_id == lead.id, Booking.status != BookingStatus.cancelled)
                .order_by(Booking.created_at.desc())
            )
        ).scalars().first()

        held_unit: tuple[str, str] | None = None
        if existing is not None:
            booking = existing
            # A wizard-started draft leaves its unit `available` until now — the
            # token reserves it as a HOLD (only if still available, so we never
            # clobber a booked/sold state) to prevent a double-booking.
            reused_unit = await self.session.get(Unit, booking.unit_id)
            if reused_unit is not None and reused_unit.status == UnitStatus.available:
                reused_unit.status = UnitStatus.hold
                held_unit = (str(reused_unit.id), str(reused_unit.project_id))
        else:
            unit = await self.session.get(Unit, capture.unit_id)
            if unit is None:
                raise ValidationError("The selected unit was not found.")
            if unit.status != UnitStatus.available:
                raise ValidationError("The selected unit is not available to book.")
            booking = Booking(unit_id=unit.id, lead_id=lead.id, status=BookingStatus.draft)
            self.session.add(booking)
            unit.status = UnitStatus.hold
            held_unit = (str(unit.id), str(unit.project_id))

        booking.token_amount = capture.token_amount
        booking.token_received_on = capture.token_received_on
        booking.token_mode = capture.token_mode
        booking.token_reference = capture.token_reference
        # held_unit → the caller broadcasts unit.status_changed after commit so
        # inventory boards / unit pickers drop the now-held unit without a refresh.
        return booking, held_unit

    async def seed_initial_transition(
        self,
        *,
        lead: Lead,
        industry: LeadIndustry,
        actor_id: UUID,
    ) -> StageTransition:
        """Auto stamp written when a lead is first created — comment is system-generated."""
        target_stage = await self.stage_repository.find(industry, lead.stage_code)
        comment = f"Lead created by user. Initial stage: {target_stage.name if target_stage else lead.stage_code}."
        transition = await self.transition_repository.create(
            {
                "lead_id": lead.id,
                "from_stage_code": None,
                "to_stage_code": lead.stage_code,
                "comment": comment,
                "performed_by_id": actor_id,
            }
        )
        lead.last_comment_preview = comment[:255]
        lead.last_comment_at = datetime.now(UTC)
        lead.stage_changed_at = datetime.now(UTC)
        return transition
