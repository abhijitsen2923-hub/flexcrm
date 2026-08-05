"""Idempotent, provider-agnostic lead ingestion for external sources (Meta, etc.).

Deliberately does NOT go through `LeadService.create_lead` / the `LeadCreate` schema:
that path requires a logged-in actor and enforces `contact_name`/`contact_phone`
min-length, which would 422 legitimate email-only Meta leads. This path takes an
already-mapped field dict (the source→CRM mapping is the caller's job), owns the
lead under the per-org integration service user, and guarantees exactly-once via
the (source_provider, external_id) partial-unique index.

Concurrency: each lead is inserted inside a SAVEPOINT so a conflict rolls back only
that one lead (not a whole poll batch). An `external_id` conflict → the record was
already ingested (idempotent skip); a `lead_number` conflict (a human created a lead
at the same instant) → retry with a fresh number. Realtime is pushed with an
EXPLICIT org_id because ingestion runs outside a request (no _broadcast_org set).
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database.enums import LeadIndustry
from app.database.pipeline_seed import initial_stage_code
from app.models.lead import Lead
from app.repositories.leads import LeadRepository
from app.services.base import ServiceBase
from app.services.realtime import realtime_manager
from app.services.stage_transitions import StageTransitionService

_PROVIDER_FALLBACK_NAME = {
    "facebook": "Facebook Lead",
    "instagram": "Instagram Lead",
    "whatsapp": "WhatsApp Lead",
}
_MAX_LEAD_NUMBER_RETRIES = 5


def _clamp_str_fields(values: dict) -> dict:
    """Truncate every string value to its Lead column's max length. External
    payloads carry arbitrary-length text (a long custom-question answer, a
    formatted phone); a VARCHAR overflow is a DataError (SQLSTATE 22001), NOT an
    IntegrityError, so it would escape the retry loop and permanently crash that
    record. This ingest layer owns length-safety (like the title/name fallbacks)."""
    for key, val in list(values.items()):
        if not isinstance(val, str):
            continue
        column = Lead.__table__.c.get(key)
        length = getattr(getattr(column, "type", None), "length", None)
        if length and len(val) > length:
            values[key] = val[:length]
    return values


class LeadIngestService(ServiceBase):
    def __init__(self, session):
        super().__init__(session)
        self.repository = LeadRepository(session)
        self.transition_service = StageTransitionService(session)

    async def find_by_external(self, source_provider: str, external_id: str) -> Lead | None:
        """Look up a lead by its external provenance. Does NOT filter soft-deleted
        rows — the partial-unique index that guarantees idempotency includes them,
        so a previously-ingested-then-deleted record must NOT be re-created (a rep
        who deleted a junk Meta lead shouldn't see it return on the next poll)."""
        return (
            await self.session.execute(
                select(Lead).where(
                    Lead.source_provider == source_provider,
                    Lead.external_id == external_id,
                )
            )
        ).scalars().first()

    async def ingest_lead(
        self,
        *,
        organization_id: UUID,
        actor_id: UUID,
        industry: LeadIndustry,
        source_provider: str,
        external_id: str,
        fields: dict,
    ) -> tuple[Lead | None, bool]:
        """Create a lead from a mapped `fields` dict, once. Returns (lead, created):
        created=False (with the existing lead) when this external record was already
        ingested. `actor_id` must be the org's integration service user."""
        existing = await self.find_by_external(source_provider, external_id)
        if existing is not None:
            return existing, False

        contact_name = (fields.get("contact_name") or "").strip() or _PROVIDER_FALLBACK_NAME.get(
            source_provider, "New Lead"
        )
        title = (fields.get("title") or "").strip() or f"{fields.get('source') or 'Lead'} — {contact_name}"
        base = {
            "industry": industry,
            "stage_code": initial_stage_code(industry.value),
            "title": title[:255],
            "contact_name": contact_name[:255],
            "contact_email": fields.get("contact_email"),
            "contact_phone": fields.get("contact_phone"),
            "company_name": fields.get("company_name"),
            "value": fields.get("value") or 0,
            "currency": (fields.get("currency") or "INR"),
            "source": fields.get("source"),
            "campaign": fields.get("campaign"),
            "interest": fields.get("interest"),
            "property_type": fields.get("property_type"),
            "budget_min": fields.get("budget_min"),
            "budget_max": fields.get("budget_max"),
            "preferred_location": fields.get("preferred_location"),
            "possession_preference": fields.get("possession_preference"),
            "notes": fields.get("notes"),
            # Triage pool: ingested leads land unassigned; a manager assigns them.
            "assigned_to_id": None,
            "source_provider": source_provider,
            "external_id": external_id,
            "created_by_id": actor_id,
            "updated_by_id": actor_id,
        }
        # Guard every bounded VARCHAR against arbitrary-length provider data so an
        # over-length value can't raise an uncaught DataError mid-savepoint.
        base = _clamp_str_fields(base)

        lead: Lead | None = None
        for _ in range(_MAX_LEAD_NUMBER_RETRIES):
            try:
                # SAVEPOINT: a conflict rolls back only this lead, leaving the rest
                # of the (per-org) batch intact.
                async with self.session.begin_nested():
                    lead = await self.repository.create(
                        {**base, "lead_number": await self.repository.next_lead_number()}
                    )
                    await self.session.flush()
                    await self.transition_service.seed_initial_transition(
                        lead=lead, industry=industry, actor_id=actor_id
                    )
                break
            except IntegrityError:
                lead = None
                # Someone ingested the SAME external record concurrently → idempotent.
                dup = await self.find_by_external(source_provider, external_id)
                if dup is not None:
                    return dup, False
                # Otherwise a lead_number collision → retry with a fresh number.
                continue

        if lead is None:
            raise RuntimeError(
                "Could not allocate a lead_number for the ingested lead after retries."
            )

        await self.commit()
        await self.invalidate_reporting_cache()
        # Ingestion has no request context, so pass org_id explicitly or the event
        # is dropped (the org-scoping fix). Owner is None — it's in the triage pool.
        await realtime_manager.broadcast(
            {
                "event": "lead.created",
                "payload": {
                    "id": str(lead.id),
                    "industry": industry.value,
                    "owner_id": None,
                    "title": lead.title,
                },
            },
            org_id=organization_id,
        )
        return lead, True
