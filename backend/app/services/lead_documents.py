"""Travel-specific document checklist (spec §3.4).

A Travel lead at the `visa_documentation_pending` stage cannot move forward
to `payment_pending` until every required document is `uploaded`. The
checklist is per-lead and lazily materialized on first access.
"""
from uuid import UUID

from sqlalchemy import select

from app.core.exceptions import NotFoundError, ValidationError
from app.database.enums import LeadIndustry
from app.models.lead import Lead
from app.models.lead_document import TRAVEL_REQUIRED_DOC_TYPES, LeadDocument
from app.services.base import ServiceBase


class LeadDocumentService(ServiceBase):
    async def list_documents(self, lead: Lead) -> list[LeadDocument]:
        result = await self.session.execute(
            select(LeadDocument).where(LeadDocument.lead_id == lead.id).order_by(LeadDocument.doc_type)
        )
        return list(result.scalars().all())

    async def ensure_checklist(self, lead: Lead) -> list[LeadDocument]:
        """Seed any missing required document rows for the lead's industry."""
        if lead.industry != LeadIndustry.travel:
            return await self.list_documents(lead)

        existing = {doc.doc_type: doc for doc in await self.list_documents(lead)}
        for doc_type in TRAVEL_REQUIRED_DOC_TYPES:
            if doc_type not in existing:
                self.session.add(LeadDocument(lead_id=lead.id, doc_type=doc_type, status="pending"))
        await self.session.flush()
        return await self.list_documents(lead)

    async def mark_uploaded(self, lead: Lead, doc_type: str, uploaded_path: str | None = None) -> LeadDocument:
        result = await self.session.execute(
            select(LeadDocument).where(
                LeadDocument.lead_id == lead.id,
                LeadDocument.doc_type == doc_type,
            )
        )
        doc = result.scalar_one_or_none()
        if doc is None:
            raise NotFoundError(f"Document '{doc_type}' is not part of the checklist for this lead.")
        from datetime import UTC, datetime

        doc.status = "uploaded"
        doc.uploaded_path = uploaded_path
        doc.uploaded_at = datetime.now(UTC)
        await self.session.flush()
        await self.commit()
        return doc

    async def assert_checklist_complete(self, lead: Lead) -> None:
        """Raise ValidationError if any required doc is still pending.

        Called by the stage transition service when moving a Travel lead OUT
        of `visa_documentation_pending`.
        """
        if lead.industry != LeadIndustry.travel:
            return
        docs = await self.list_documents(lead)
        uploaded = {doc.doc_type for doc in docs if doc.status == "uploaded"}
        missing = [d for d in TRAVEL_REQUIRED_DOC_TYPES if d not in uploaded]
        if missing:
            raise ValidationError(
                "Cannot leave 'Visa/Documentation Pending' until all required documents are uploaded. "
                f"Missing: {', '.join(missing)}."
            )


async def get_lead_or_404(session, lead_id: UUID) -> Lead:
    from app.repositories.leads import LeadRepository

    lead = await LeadRepository(session).get(lead_id)
    if lead is None:
        raise NotFoundError("Lead not found.")
    return lead
