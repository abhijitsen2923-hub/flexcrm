import re
from uuid import UUID

from fastapi import BackgroundTasks

from sqlalchemy import select

from app.core.currencies import DEFAULT_CURRENCY, allowed_currencies_for_org
from app.core.exceptions import NotFoundError, ValidationError
from app.core.tenancy import current_org
from app.database.enums import LeadIndustry
from app.database.pipeline_seed import initial_stage_code
from app.models.organization import Organization
from app.repositories.customers import CustomerRepository
from app.repositories.leads import LeadRepository
from app.repositories.users import UserRepository
from app.schemas.common import PaginationParams
from app.schemas.lead import LeadCreate, LeadDuplicate, LeadFilterParams, LeadUpdate
from app.services.base import ServiceBase
from app.services.email import EmailService
from app.services.notifications import NotificationService
from app.services.realtime import realtime_manager
from app.services.stage_transitions import StageTransitionService
from app.utils.query import validate_sort_field


class LeadService(ServiceBase):
    allowed_sort_fields = {
        "created_at",
        "updated_at",
        "title",
        "stage_code",
        "value",
        "probability",
        "expected_close_date",
        "lead_number",
        "last_comment_at",
    }

    def __init__(self, session):
        super().__init__(session)
        self.repository = LeadRepository(session)
        self.customer_repository = CustomerRepository(session)
        self.user_repository = UserRepository(session)
        self.notification_service = NotificationService(session)
        self.email_service = EmailService()
        self.transition_service = StageTransitionService(session)

    async def list_leads(self, pagination: PaginationParams, filters: LeadFilterParams):
        sort_by = validate_sort_field(filters.sort_by, self.allowed_sort_fields)
        items, total = await self.repository.list(
            pagination=pagination,
            filters={
                "customer_id": filters.customer_id,
                "industry": filters.industry,
                "stage_code": filters.stage_code,
                "source": filters.source,
                "assigned_to_id": filters.assigned_to_id,
            },
            search=filters.search,
            search_fields=("title", "interest"),
            sort_by=sort_by,
            sort_order=filters.sort_order,
            options=self.repository.default_options,
        )
        # Flag leads that share an email/phone with another active lead so the
        # UI can show a duplicate ("!") marker. Two aggregate queries, then a
        # transient attribute LeadRead reads via from_attributes.
        dup_emails, dup_phones = await self.repository.duplicate_contact_keys()
        for lead in items:
            email_key = lead.contact_email.lower() if lead.contact_email else None
            phone_key = re.sub(r"\D", "", lead.contact_phone) if lead.contact_phone else ""
            lead.is_duplicate = bool(
                (email_key and email_key in dup_emails)
                or (phone_key and phone_key in dup_phones)
            )
        return items, total

    async def get_lead(self, lead_id: UUID):
        lead = await self.repository.get(lead_id, options=self.repository.default_options)
        if lead is None:
            raise NotFoundError("Lead not found.")
        return lead

    async def find_duplicate_leads(
        self, email: str | None, phone: str | None
    ) -> list[LeadDuplicate]:
        """Warn-but-allow duplicate check: active leads in this tenant whose
        email (case-insensitive) or phone (digits-only) matches. Never blocks."""
        norm_email = email.strip().lower() if email and email.strip() else None
        phone_digits = re.sub(r"\D", "", phone) if phone else ""
        rows = await self.repository.find_duplicates(norm_email, phone_digits or None)
        return [LeadDuplicate.model_validate(row) for row in rows]

    async def create_lead(
        self,
        payload: LeadCreate,
        *,
        actor_id: UUID,
        actor_business_type: LeadIndustry | None = None,
        background_tasks: BackgroundTasks | None = None,
    ):
        # customer_id is optional now: a Lead can be created with just contact
        # details, and a Customer row is materialized later when the lead hits
        # the Sold stage.
        await self._ensure_references(payload.customer_id, payload.assigned_to_id)

        # Industry resolution priority:
        # 1. Explicit `industry` on the request (admin/manager override).
        # 2. The current user's `business_type` (chosen at registration).
        # 3. Reject — we can't pick an industry for them.
        industry = payload.industry or actor_business_type
        if industry is None:
            raise ValidationError(
                "Cannot determine the lead's industry. Set your account's business_type "
                "(via registration) or pass `industry` explicitly."
            )

        # Validate currency against the org's allow-list. We pull the org
        # row directly (with the tenancy filter still active — the user's
        # session is scoped to their own org, so the lookup naturally
        # returns the right row). For unscoped contexts (which only happens
        # in tests creating leads outside an org), fall back to INR.
        org_id = current_org(self.session)
        requested_currency = (payload.currency or DEFAULT_CURRENCY).upper()
        if org_id is not None:
            org = (
                await self.session.execute(select(Organization).where(Organization.id == org_id))
            ).scalar_one_or_none()
            if org is not None:
                allowed = allowed_currencies_for_org(org)
                if requested_currency not in allowed:
                    raise ValidationError(
                        f"Currency '{requested_currency}' is not enabled for this organization. "
                        f"Allowed: {', '.join(allowed)}."
                    )

        initial_code = initial_stage_code(industry.value)
        lead_number = await self.repository.next_lead_number()
        lead = await self.repository.create(
            {
                "customer_id": payload.customer_id,
                "industry": industry,
                "stage_code": initial_code,
                "lead_number": lead_number,
                "title": payload.title,
                "contact_name": payload.contact_name,
                "contact_email": payload.contact_email,
                "contact_phone": payload.contact_phone,
                "company_name": payload.company_name,
                "value": payload.value,
                "currency": requested_currency,
                "probability": payload.probability,
                "expected_close_date": payload.expected_close_date,
                "source": payload.source,
                "interest": payload.interest,
                "assigned_to_id": payload.assigned_to_id,
                "created_by_id": actor_id,
                "updated_by_id": actor_id,
            }
        )
        await self.transition_service.seed_initial_transition(
            lead=lead, industry=industry, actor_id=actor_id
        )
        if payload.assigned_to_id:
            await self._notify_assignee(
                payload.assigned_to_id, f"Lead assigned: {payload.title}", payload.title, background_tasks
            )
        await self.commit()
        await self.invalidate_reporting_cache()
        lead = await self.get_lead(lead.id)
        await realtime_manager.broadcast(
            {
                "event": "lead.created",
                "payload": {
                    "id": str(lead.id),
                    "industry": lead.industry.value,
                    "owner_id": str(lead.assigned_to_id) if lead.assigned_to_id else None,
                    "title": lead.title,
                },
            }
        )
        return lead

    async def update_lead(
        self,
        lead_id: UUID,
        payload: LeadUpdate,
        *,
        actor_id: UUID,
        background_tasks: BackgroundTasks | None = None,
    ):
        lead = await self.get_lead(lead_id)
        update_data = payload.model_dump(exclude_unset=True)
        await self._ensure_references(update_data.get("customer_id"), update_data.get("assigned_to_id"))
        update_data["updated_by_id"] = actor_id
        lead = await self.repository.update(lead, update_data)
        if update_data.get("assigned_to_id"):
            await self._notify_assignee(
                update_data["assigned_to_id"], f"Lead assigned: {lead.title}", lead.title, background_tasks
            )
        await self.commit()
        await self.invalidate_reporting_cache()
        lead = await self.get_lead(lead.id)
        await realtime_manager.broadcast({"event": "lead.updated", "payload": {"id": str(lead.id), "title": lead.title}})
        return lead

    async def delete_lead(self, lead_id: UUID, *, actor_id: UUID):
        lead = await self.get_lead(lead_id)
        await self.repository.soft_delete(lead, actor_id)
        await self.commit()
        await self.invalidate_reporting_cache()
        await realtime_manager.broadcast({"event": "lead.deleted", "payload": {"id": str(lead.id)}})

    async def _ensure_references(self, customer_id: UUID | None, assigned_to_id: UUID | None) -> None:
        if customer_id:
            customer = await self.customer_repository.get(customer_id)
            if customer is None:
                raise NotFoundError("Customer not found.")
        if assigned_to_id:
            assignee = await self.user_repository.get(assigned_to_id)
            if assignee is None:
                raise NotFoundError("Assigned user not found.")

    async def _notify_assignee(
        self,
        assignee_id: UUID,
        message: str,
        resource_title: str,
        background_tasks: BackgroundTasks | None,
    ) -> None:
        assignee = await self.user_repository.get(assignee_id)
        if assignee is None:
            return
        await self.notification_service.create_notification(user_id=assignee_id, message=message)
        if background_tasks:
            background_tasks.add_task(
                self.email_service.send_assignment_email,
                assignee.email,
                assignee.first_name,
                resource_title,
            )
