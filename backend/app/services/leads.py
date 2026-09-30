import re
from datetime import UTC, datetime
from uuid import UUID

from fastapi import BackgroundTasks

from sqlalchemy import or_, select, update

from app.core.currencies import DEFAULT_CURRENCY, allowed_currencies_for_org
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.lead_intent import INTENT_NOT_RATED, LEAD_INTENTS, stage_locks_intent
from app.core.tenancy import current_org
from app.database.enums import LeadIndustry
from app.database.pipeline_seed import initial_stage_code
from app.models.lead import Lead, LeadCallLog
from app.models.organization import Organization
from app.repositories.customers import CustomerRepository
from app.repositories.leads import LeadRepository
from app.repositories.pipeline_stages import PipelineStageRepository
from app.repositories.users import UserRepository
from app.schemas.common import PaginationParams
from app.schemas.lead import LeadCreate, LeadDuplicate, LeadFilterParams, LeadUpdate
from app.core.campaign_names import campaign_key
from app.services.base import ServiceBase
from app.services.campaigns import CampaignService, CampaignWritePolicy
from app.services.email import EmailService
from app.services.lead_assignments import LeadAssignmentService
from app.services.lead_intents import LeadIntentService
from app.services.notifications import NotificationService
from app.services.realtime import realtime_manager
from app.services.stage_transitions import StageTransitionService
from app.utils.query import validate_sort_field

# A search that is just a lead number: optional "#", then 1-9 ASCII digits without a leading zero (a leading
# zero is a phone fragment; ≤ 9 digits always fits the INTEGER column — a longer value would make Postgres
# raise instead of falling back to the normal search).
_LEAD_NUMBER_SEARCH = re.compile(r"#?\s*([1-9][0-9]{0,8})")
_LEAD_SEARCH_FIELDS = (
    "title",
    "interest",
    "contact_name",
    "contact_email",
    "contact_phone",
    "contact_phone_alt",
    "lead_number",
)


def lead_number_from_search(term: str | None) -> int | None:
    """"92422" / "#92422" → 92422; anything else (phone numbers, text, 10+ digits) → None."""
    match = _LEAD_NUMBER_SEARCH.fullmatch(term.strip()) if term else None
    return int(match.group(1)) if match else None


def _intent_filter_clause(raw: str | None):
    """"high,medium" / "none" (comma-joined) → one OR clause over Lead.intent; None when no intent filter.
    Case and spaces don't matter; an unknown value is a 422 (not silently ignored)."""
    tokens = {t.strip().lower() for t in (raw or "").split(",") if t.strip()}
    if not tokens:
        return None
    unknown = tokens - {*LEAD_INTENTS, INTENT_NOT_RATED}
    if unknown:
        raise ValidationError(
            f"Unknown intent filter {', '.join(sorted(unknown))!s} — use high, medium, low or none."
        )
    rated = sorted(tokens & set(LEAD_INTENTS))
    clauses = []
    if rated:
        clauses.append(Lead.intent.in_(rated))
    if INTENT_NOT_RATED in tokens:
        clauses.append(Lead.intent.is_(None))
    return or_(*clauses)


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
        "next_action_date",
    }

    def __init__(self, session):
        super().__init__(session)
        self.repository = LeadRepository(session)
        # Campaign name resolution memo for this service's lifetime (a CSV import reuses one instance for
        # every row). Cleared by the importer when a row rolls back.
        self._campaign_names: dict[tuple[str, CampaignWritePolicy], str | None] = {}
        self.customer_repository = CustomerRepository(session)
        self.user_repository = UserRepository(session)
        self.notification_service = NotificationService(session)
        self.email_service = EmailService()
        self.transition_service = StageTransitionService(session)
        self.assignment_service = LeadAssignmentService(session)
        self.intent_service = LeadIntentService(session)

    async def bulk_reassign(self, lead_ids: list[UUID], assigned_to_id: UUID, *, actor_id: UUID | None) -> int:
        """Reassign the owner of many leads at once (Manager bulk action).

        Returns the number of leads updated. Notifies the new owner once with the
        count so they know their queue grew.
        """
        if not lead_ids:
            return 0
        # Guard against cross-tenant assignment: the target owner must be a user
        # in THIS org. `users` is a shared table, so an unscoped id could point
        # at another tenant's user (IDOR). See UserRepository.get_in_org.
        assignee = await self.user_repository.get_in_org(assigned_to_id, current_org(self.session))
        if assignee is None:
            raise NotFoundError("Assigned user not found.")
        # Read each lead's CURRENT owner first (row-locked until commit, so it can't change underneath
        # us) — the single UPDATE below can't return it — and log every real owner change.
        previous_owners = (
            await self.session.execute(
                select(Lead.id, Lead.assigned_to_id)
                .where(Lead.id.in_(lead_ids), Lead.is_deleted.is_(False))
                .order_by(Lead.id)  # consistent lock order, so overlapping bulk reassigns can't deadlock
                .with_for_update()
            )
        ).all()
        for changed_lead_id, previous_owner_id in previous_owners:
            self.assignment_service.record(
                lead_id=changed_lead_id,
                from_user_id=previous_owner_id,
                to_user_id=assigned_to_id,
                actor_id=actor_id,
                source="bulk_reassign",
            )
        result = await self.session.execute(
            update(Lead)
            .where(Lead.id.in_(lead_ids), Lead.is_deleted.is_(False))
            .values(assigned_to_id=assigned_to_id, updated_by_id=actor_id)
        )
        count = result.rowcount or 0
        if count:
            await self.notification_service.create_notification(
                user_id=assigned_to_id,
                message=f"{count} lead{'s' if count != 1 else ''} assigned to you.",
            )
        await self.commit()
        if count:
            # A bulk owner change alters the dashboard/analytics summary counts
            # (both the new owner's own-scoped tile and the org/manager view) and
            # any open leads list. Mirror the single-lead path so those refresh
            # immediately instead of serving the pre-assignment values until the
            # 5-minute reporting-cache TTL lapses.
            await self.invalidate_reporting_cache()
            await realtime_manager.broadcast(
                {"event": "lead.reassigned", "payload": {"count": count, "assigned_to_id": str(assigned_to_id)}}
            )
        return count

    async def log_call(
        self,
        lead_id: UUID,
        call_type: str,
        *,
        actor_id: UUID,
        notes: str | None = None,
        next_action_date: datetime | None = None,
    ) -> LeadCallLog:
        """Record a call by the current user. 'first_call' is idempotent per
        (lead, user) — clicking it again returns the existing log rather than
        stacking duplicates. When `next_action_date` is given (e.g. a DNP →
        schedule the next call), it's denormalized onto lead.next_action_date so
        it feeds the leads date-filter + follow-up reminders. A `notes` reason is
        denormalized onto last_comment_preview (mirroring a stage transition) so
        it surfaces on the reminder digest + the lead's "last comment"."""
        if call_type == "first_call":
            existing = await self.session.scalar(
                select(LeadCallLog).where(
                    LeadCallLog.lead_id == lead_id,
                    LeadCallLog.user_id == actor_id,
                    LeadCallLog.call_type == "first_call",
                )
            )
            if existing is not None:
                return existing
        log = LeadCallLog(
            lead_id=lead_id, user_id=actor_id, call_type=call_type, notes=notes, next_action_date=next_action_date
        )
        self.session.add(log)
        # Denormalize onto the lead: the scheduled callback (next_action_date) and
        # the reason (notes → last_comment_preview) so the leads date-filter,
        # follow-up reminders, and the "last comment" snapshot reflect this call —
        # the same way a stage transition denormalizes. A blank field leaves the
        # prior value untouched (a note-less follow-up shouldn't wipe last_comment).
        # Gate on the *stripped* note so a whitespace-only value (possible from a
        # raw API caller — the schema has no min length) can't erase a real preview.
        note = notes.strip() if notes else ""
        if next_action_date is not None or note:
            lead = await self.session.get(Lead, lead_id)
            if lead is not None:
                if next_action_date is not None:
                    lead.next_action_date = next_action_date
                if note:
                    lead.last_comment_preview = note[:255]
                    lead.last_comment_at = datetime.now(UTC)
        await self.commit()
        # Re-query so the `user` relationship (selectin) is loaded for the response
        # — accessing an unloaded relationship after commit would lazy-load in the
        # async context and raise.
        return await self.session.scalar(select(LeadCallLog).where(LeadCallLog.id == log.id))

    async def list_calls(self, lead_id: UUID) -> list[LeadCallLog]:
        result = await self.session.execute(
            select(LeadCallLog).where(LeadCallLog.lead_id == lead_id).order_by(LeadCallLog.created_at)
        )
        return list(result.scalars().all())

    async def list_campaigns(self, owner_id=None) -> list[str]:
        """Campaigns in use on the tenant's leads, one canonical name per campaign — for the list's
        Campaign filter. `owner_id` scopes the result to a front-line rep's own leads (BR-2)."""
        values = await self.repository.distinct_campaigns(owner_id=owner_id)
        return await CampaignService(self.session).canonical_names(values)

    async def _resolve_campaign(self, raw: str | None, policy: CampaignWritePolicy) -> str | None:
        """The tenant's canonical campaign name for `raw` (see CampaignService.resolve), memoised per key."""
        memo_key = (campaign_key(raw), policy)
        if not memo_key[0]:
            return None
        if memo_key not in self._campaign_names:
            self._campaign_names[memo_key] = await CampaignService(self.session).resolve(raw, policy)
        return self._campaign_names[memo_key]

    def forget_campaign_names(self) -> None:
        """Drop the memo — after a rollback, a campaign it remembers may have been rolled back too."""
        self._campaign_names.clear()

    async def list_leads(
        self,
        pagination: PaginationParams,
        filters: LeadFilterParams,
        *,
        reveal_duplicate_owner: bool = True,
    ):
        sort_by = validate_sort_field(filters.sort_by, self.allowed_sort_fields)
        # Stage filter accepts a single code or a comma-joined list (multi-select) →
        # a list value makes the repo emit `stage_code IN (...)`.
        stage_codes = (
            [c.strip() for c in filters.stage_code.split(",") if c.strip()]
            if filters.stage_code
            else None
        )
        # "Due on a day" filter — a datetime range the generic equality/IN builder
        # can't express. The client sends the selected local day's UTC boundaries.
        extra_filters = []
        if filters.next_action_from is not None:
            extra_filters.append(Lead.next_action_date >= filters.next_action_from)
        if filters.next_action_to is not None:
            extra_filters.append(Lead.next_action_date < filters.next_action_to)
        # Latest-stage-change range (independent of next_action) — same half-open
        # local-day boundaries from the client.
        if filters.stage_changed_from is not None:
            extra_filters.append(Lead.stage_changed_at >= filters.stage_changed_from)
        if filters.stage_changed_to is not None:
            extra_filters.append(Lead.stage_changed_at < filters.stage_changed_to)
        # Lead-date range (when the lead came in) — ANDed with every other filter.
        if filters.created_from is not None:
            extra_filters.append(Lead.created_at >= filters.created_from)
        if filters.created_to is not None:
            extra_filters.append(Lead.created_at < filters.created_to)
        # Unassigned (triage) filter — IS NULL can't be expressed by the generic
        # equality/IN builder, so it goes through extra_filters (applied to both the
        # row query and the count, keeping pagination totals correct).
        if filters.unassigned:
            extra_filters.append(Lead.assigned_to_id.is_(None))
        # Intent: one or several of high / medium / low, and "none" for not-rated leads (IS NULL — like
        # "unassigned", the generic builder can't express it, so it's one OR clause here).
        intent_clause = _intent_filter_clause(filters.intent)
        if intent_clause is not None:
            extra_filters.append(intent_clause)
        list_args = dict(
            pagination=pagination,
            filters={
                "customer_id": filters.customer_id,
                "industry": filters.industry,
                "stage_code": stage_codes or None,
                "source": filters.source,
                # Any spelling of a campaign (case / spaces / merged or renamed old name) finds its leads.
                "campaign": (
                    await CampaignService(self.session).filter_values(filters.campaign)
                    if filters.campaign
                    else None
                ),
                "assigned_to_id": filters.assigned_to_id,
                "partner_id": filters.partner_id,
            },
            sort_by=sort_by,
            sort_order=filters.sort_order,
            options=self.repository.default_options,
        )
        # Searching a lead number ("92422" / "#92422") shows THAT lead — not also every lead whose phone
        # happens to contain those digits. Same filters and rep scoping as the normal search; when no such
        # lead is visible (none, another rep's, deleted, filtered out) it falls back to the normal search.
        # Decided on `total`, not this page's items, so page 2 of an exact hit doesn't flip to the fallback.
        items, total = [], 0
        lead_number = lead_number_from_search(filters.search)
        if lead_number is not None:
            items, total = await self.repository.list(
                **list_args, extra_filters=[*extra_filters, Lead.lead_number == lead_number]
            )
        if not total:
            items, total = await self.repository.list(
                **list_args,
                extra_filters=extra_filters,
                search=filters.search,
                # Free-text search spans title + interest + the contact fields + lead
                # number (lead_number is Integer — the repo casts to String for ILIKE).
                search_fields=_LEAD_SEARCH_FIELDS,
            )
        # Flag leads that share an email/phone with another active lead so the
        # UI can show a duplicate ("!") marker. Two aggregate queries, then a
        # transient attribute LeadRead reads via from_attributes.
        dup_emails, dup_phones = await self.repository.duplicate_contact_keys()
        assign_map = await self.repository.duplicate_assignment_map(dup_phones) if dup_phones else {}
        for lead in items:
            email_key = lead.contact_email.lower() if lead.contact_email else None
            phone_key = re.sub(r"\D", "", lead.contact_phone) if lead.contact_phone else ""
            lead.is_duplicate = bool(
                (email_key and email_key in dup_emails)
                or (phone_key and phone_key in dup_phones)
            )
            # Fresh vs already-assigned label for a shared phone NUMBER: look at the
            # OTHER matching leads — if any is assigned, the number is already given to
            # that owner (name withheld from reps); otherwise it's fresh (unowned).
            lead.duplicate_status = None
            lead.duplicate_owner = None
            if phone_key and phone_key in dup_phones:
                others_assigned = [
                    (lid, name) for (lid, name) in assign_map.get(phone_key, []) if lid != lead.id
                ]
                if others_assigned:
                    lead.duplicate_status = "assigned"
                    if reveal_duplicate_owner:
                        lead.duplicate_owner = others_assigned[0][1] or None
                else:
                    lead.duplicate_status = "fresh"
        return items, total

    async def get_lead(self, lead_id: UUID):
        lead = await self.repository.get(lead_id, options=self.repository.default_options)
        if lead is None:
            raise NotFoundError("Lead not found.")
        return lead

    async def find_duplicate_leads(
        self, email: str | None, phone: str | None, owner_id=None
    ) -> list[LeadDuplicate]:
        """Warn-but-allow duplicate check: active leads in this tenant whose
        email (case-insensitive) or phone (digits-only) matches. Never blocks.
        `owner_id` restricts the search to that owner (front-line rep scoping)."""
        norm_email = email.strip().lower() if email and email.strip() else None
        phone_digits = re.sub(r"\D", "", phone) if phone else ""
        rows = await self.repository.find_duplicates(norm_email, phone_digits or None, owner_id=owner_id)
        return [LeadDuplicate.model_validate(row) for row in rows]

    async def create_lead(
        self,
        payload: LeadCreate,
        *,
        actor_id: UUID,
        actor_business_type: LeadIndustry | None = None,
        background_tasks: BackgroundTasks | None = None,
        assignment_source: str = "created",
        campaign_policy: CampaignWritePolicy | None = None,
        notify_assignee: bool = True,
        reload: bool = True,
    ):
        """`notify_assignee=False` / `reload=False` are for the CSV importer: it sends ONE summary notification
        per assignee at the end, and doesn't need the eager-loaded copy of every lead it creates."""
        # customer_id is optional now: a Lead can be created with just contact
        # details, and a Customer row is materialized later when the lead hits
        # the Sold stage.
        await self._ensure_references(payload.customer_id, payload.assigned_to_id)

        # Industry is PINNED to the org's business_type. An org is single-industry
        # (Organization.business_type, non-nullable), so every lead MUST match it.
        # We deliberately ignore payload.industry and the deprecated per-user
        # business_type here: trusting those let a manual create stamp a lead with
        # the wrong vertical (e.g. a real-estate lead marked "education"), which
        # then disappears from industry-scoped admin views. `actor_business_type`
        # is used only as a fallback for unscoped contexts (tests that create leads
        # outside an org). We pull the org row directly — the session's tenancy
        # filter scopes it to the caller's own org.
        org_id = current_org(self.session)
        org = None
        if org_id is not None:
            org = (
                await self.session.execute(select(Organization).where(Organization.id == org_id))
            ).scalar_one_or_none()
        industry = (org.business_type if org is not None else None) or actor_business_type
        if industry is None:
            raise ValidationError(
                "Cannot determine the lead's industry — this organization has no business type set."
            )

        # Validate currency against the org's allow-list (same org row). Unscoped
        # contexts (tests) skip the check and fall back to INR.
        requested_currency = (payload.currency or DEFAULT_CURRENCY).upper()
        if org is not None:
            allowed = allowed_currencies_for_org(org)
            if requested_currency not in allowed:
                raise ValidationError(
                    f"Currency '{requested_currency}' is not enabled for this organization. "
                    f"Allowed: {', '.join(allowed)}."
                )

        initial_code = initial_stage_code(industry.value)
        # The tenant's canonical campaign name (after validation, so a rejected lead never adds one). No
        # policy = strict: an unknown name is rejected unless the caller says the actor may add campaigns.
        campaign = await self._resolve_campaign(
            payload.campaign, campaign_policy or CampaignWritePolicy.manual(can_manage=False, actor_id=actor_id)
        )
        lead_number = await self.repository.next_lead_number()
        lead = await self.repository.create(
            {
                "customer_id": payload.customer_id,
                "industry": industry,
                "stage_code": initial_code,
                "lead_number": lead_number,
                "title": payload.title,
                "salutation": payload.salutation,
                "contact_name": payload.contact_name,
                "contact_email": payload.contact_email,
                "contact_phone": payload.contact_phone,
                "contact_phone_alt": payload.contact_phone_alt,
                "company_name": payload.company_name,
                "value": payload.value,
                "currency": requested_currency,
                "probability": payload.probability,
                "expected_close_date": payload.expected_close_date,
                "source": payload.source,
                "campaign": campaign,
                "intent": payload.intent,
                "interest": payload.interest,
                "assigned_to_id": payload.assigned_to_id,
                "partner_id": payload.partner_id,
                # Real-estate fields were previously dropped on create — persist
                # them so Budget (which replaces Value for real estate) is saved.
                "property_type": payload.property_type,
                "budget_min": payload.budget_min,
                "budget_max": payload.budget_max,
                "preferred_location": payload.preferred_location,
                "possession_preference": payload.possession_preference,
                "notes": payload.notes,
                "created_by_id": actor_id,
                "updated_by_id": actor_id,
            }
        )
        await self.transition_service.seed_initial_transition(
            lead=lead, industry=industry, actor_id=actor_id
        )
        # Initial owner (manual create or CSV upload) starts the lead's assignment history.
        self.assignment_service.record(
            lead_id=lead.id,
            from_user_id=None,
            to_user_id=payload.assigned_to_id,
            actor_id=actor_id,
            source=assignment_source,
        )
        # A starting intent (New Lead form / CSV column) begins the lead's intent history.
        self.intent_service.record(
            lead_id=lead.id,
            from_intent=None,
            to_intent=payload.intent,
            actor_id=actor_id,
            source="import" if assignment_source == "import" else "created",
        )
        if payload.assigned_to_id and notify_assignee:
            await self._notify_assignee(
                payload.assigned_to_id, f"Lead assigned: {payload.title}", payload.title, background_tasks
            )
        await self.commit()
        await self.invalidate_reporting_cache()
        if reload:
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
        campaign_policy: CampaignWritePolicy | None = None,
    ):
        lead = await self.get_lead(lead_id)
        update_data = payload.model_dump(exclude_unset=True)
        # A lead's industry is fixed to the org's (single-industry) — never let a
        # PUT change it to a mismatched vertical. (stage_code is likewise blocked,
        # at the endpoint.)
        update_data.pop("industry", None)
        if "campaign" in update_data:
            if campaign_key(update_data["campaign"]) == campaign_key(lead.campaign):
                # Same campaign (any spelling) — leave it; an unchanged legacy/inactive value never 422s.
                update_data.pop("campaign")
            else:
                update_data["campaign"] = await self._resolve_campaign(
                    update_data["campaign"],
                    campaign_policy or CampaignWritePolicy.manual(can_manage=False, actor_id=actor_id),
                )
        await self._ensure_references(update_data.get("customer_id"), update_data.get("assigned_to_id"))
        update_data["updated_by_id"] = actor_id
        if "assigned_to_id" in update_data:
            # Re-read the CURRENT owner under a row lock (held until commit): the lead loaded above can be
            # stale if someone else reassigned it meanwhile, which would log the wrong "from".
            previous_owner_id = await self.session.scalar(
                select(Lead.assigned_to_id).where(Lead.id == lead.id).with_for_update()
            )
            self.assignment_service.record(
                lead_id=lead.id,
                from_user_id=previous_owner_id,
                to_user_id=update_data["assigned_to_id"],
                actor_id=actor_id,
                source="reassign",
            )
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

    async def set_intent(self, lead_id: UUID, intent: str, *, actor_id: UUID):
        """Lead details → change the intent without moving the stage. Refused once the intent is fixed
        (Booked / Token onward, closed stages). An unchanged intent is a no-op."""
        lead = await self.get_lead(lead_id)
        # Lock the lead row (held until commit) and re-read what we check and change: the loaded object can be
        # stale (a stage move or another quick change may have committed meanwhile). Serialises quick changes
        # and stage moves on this lead, so the "fixed" check and the history's "from" are exact.
        await self.session.refresh(lead, attribute_names=["intent", "stage_code"], with_for_update=True)
        stage = await PipelineStageRepository(self.session).find(lead.industry, lead.stage_code)
        if stage is not None and stage_locks_intent(stage):
            raise ConflictError(
                f"This lead's intent is fixed at its current stage ({stage.name}) and can't be changed."
            )
        previous = lead.intent
        if previous == intent:
            return lead
        self.intent_service.record(
            lead_id=lead.id, from_intent=previous, to_intent=intent, actor_id=actor_id, source="quick_set"
        )
        lead.intent = intent
        lead.updated_by_id = actor_id
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
            assignee = await self.user_repository.get_in_org(assigned_to_id, current_org(self.session))
            if assignee is None:
                raise NotFoundError("Assigned user not found.")

    async def _notify_assignee(
        self,
        assignee_id: UUID,
        message: str,
        resource_title: str,
        background_tasks: BackgroundTasks | None,
    ) -> None:
        assignee = await self.user_repository.get_in_org(assignee_id, current_org(self.session))
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
