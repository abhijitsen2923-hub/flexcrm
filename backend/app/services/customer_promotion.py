"""Auto-promote a Lead into a Customer when it reaches the Sold stage.

Triggered from `StageTransitionService.create_transition` after the stage
move is persisted. Idempotent — leads already linked to a Customer are
re-activated rather than duplicated.
"""
from datetime import UTC, datetime
from uuid import UUID

from app.database.enums import CustomerLifecycleStage, CustomerStatus
from app.models.customer import Customer
from app.models.lead import Lead
from app.repositories.customers import CustomerRepository
from app.services.base import ServiceBase
from app.services.customer_lifecycle import claim_customer_number
from app.services.realtime import realtime_manager


class CustomerPromotionService(ServiceBase):
    def __init__(self, session):
        super().__init__(session)
        self.customer_repository = CustomerRepository(session)

    async def promote_from_lead(self, lead: Lead, *, actor_id: UUID) -> Customer:
        if lead.customer_id is not None:
            existing = await self.customer_repository.get(lead.customer_id)
            if existing is not None:
                existing.status = CustomerStatus.active
                # Re-onboard on a re-sold transition; the health job will
                # promote it back to `active` once activity resumes.
                existing.lifecycle_stage = CustomerLifecycleStage.onboarding
                existing.onboarding_started_at = datetime.now(UTC)
                existing.updated_by_id = actor_id
                if existing.source_lead_id is None:
                    existing.source_lead_id = lead.id
                if existing.original_owner_id is None and lead.assigned_to_id is not None:
                    existing.original_owner_id = lead.assigned_to_id
                if existing.current_owner_id is None and lead.assigned_to_id is not None:
                    existing.current_owner_id = lead.assigned_to_id
                await self.session.flush()
                await realtime_manager.broadcast(
                    {
                        "event": "customer.promoted",
                        "payload": {
                            "customer_id": str(existing.id),
                            "lead_id": str(lead.id),
                            "by_user_id": str(actor_id),
                        },
                    }
                )
                return existing

        # New customer from the lead's embedded contact info.
        company_name = lead.company_name or lead.contact_name
        new_customer = await self.customer_repository.create(
            {
                "company_name": company_name,
                "contact_name": lead.contact_name,
                "email": lead.contact_email,
                "phone": lead.contact_phone,
                "source": lead.source,
                "status": CustomerStatus.active,
                "lifecycle_stage": CustomerLifecycleStage.onboarding,
                "customer_number": await claim_customer_number(self.session),
                "onboarding_started_at": datetime.now(UTC),
                "original_owner_id": lead.assigned_to_id,
                "current_owner_id": lead.assigned_to_id,
                "source_lead_id": lead.id,
                "created_by_id": actor_id,
                "updated_by_id": actor_id,
            }
        )
        lead.customer_id = new_customer.id
        lead.updated_by_id = actor_id
        await self.session.flush()

        await realtime_manager.broadcast(
            {
                "event": "customer.promoted",
                "payload": {
                    "customer_id": str(new_customer.id),
                    "lead_id": str(lead.id),
                    "by_user_id": str(actor_id),
                },
            }
        )
        return new_customer
