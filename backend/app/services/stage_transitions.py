from datetime import UTC, datetime
from uuid import UUID

from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.core.permissions import STAGE_MANAGER_ROLES, can_set_stage
from app.database.enums import LeadIndustry, PipelineStageCategory, UserRole
from app.models.lead import Lead
from app.models.pipeline_stage import PipelineStage  # noqa: F401  (kept for type hinting context)
from app.models.stage_transition import StageTransition
from app.repositories.leads import LeadRepository
from app.repositories.pipeline_stages import PipelineStageRepository
from app.repositories.stage_transitions import StageTransitionRepository
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


# The "Sold" stage shares the same `code` slug across both industries
# (Education position 12 and Travel position 12). One constant covers both.
SOLD_STAGE_CODE = "sold"

# Travel-only gate: cannot leave this stage until all required docs are uploaded.
TRAVEL_DOCS_PENDING_STAGE = "visa_documentation_pending"

# Closed-lost stages — any move out of these is a "reopen" and skips the
# normal backward-only-by-manager rule.
CLOSED_LOST_STAGE_CODES = {"did_not_pick", "not_interested", "disqualified"}


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
            # transition with an existing order won't double-accrue. Local import
            # to avoid a circular import at module load.
            if order is not None:
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
        return transition

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
        return transition
