from uuid import UUID

from app.core.exceptions import NotFoundError
from app.repositories.customers import CustomerRepository
from app.repositories.deals import DealRepository
from app.schemas.common import PaginationParams
from app.schemas.deal import DealCreate, DealFilterParams, DealUpdate
from app.services.base import ServiceBase
from app.services.realtime import realtime_manager
from app.utils.query import validate_sort_field


class DealService(ServiceBase):
    allowed_sort_fields = {"created_at", "updated_at", "title", "amount", "stage", "expected_close", "status"}

    def __init__(self, session):
        super().__init__(session)
        self.repository = DealRepository(session)
        self.customer_repository = CustomerRepository(session)

    async def list_deals(self, pagination: PaginationParams, filters: DealFilterParams):
        sort_by = validate_sort_field(filters.sort_by, self.allowed_sort_fields)
        return await self.repository.list(
            pagination=pagination,
            filters={
                "customer_id": filters.customer_id,
                "stage": filters.stage,
                "status": filters.status,
            },
            search=filters.search,
            search_fields=("title",),
            sort_by=sort_by,
            sort_order=filters.sort_order,
            options=self.repository.default_options,
        )

    async def get_deal(self, deal_id: UUID):
        deal = await self.repository.get(deal_id, options=self.repository.default_options)
        if deal is None:
            raise NotFoundError("Deal not found.")
        return deal

    async def create_deal(self, payload: DealCreate, *, actor_id: UUID):
        await self._ensure_customer(payload.customer_id)
        deal = await self.repository.create(
            {
                **payload.model_dump(),
                "created_by_id": actor_id,
                "updated_by_id": actor_id,
            }
        )
        await self.commit()
        await self.invalidate_reporting_cache()
        deal = await self.get_deal(deal.id)
        await realtime_manager.broadcast({"event": "deal.created", "payload": {"id": str(deal.id), "title": deal.title}})
        return deal

    async def update_deal(self, deal_id: UUID, payload: DealUpdate, *, actor_id: UUID):
        deal = await self.get_deal(deal_id)
        update_data = payload.model_dump(exclude_unset=True)
        if update_data.get("customer_id"):
            await self._ensure_customer(update_data["customer_id"])
        update_data["updated_by_id"] = actor_id
        deal = await self.repository.update(deal, update_data)
        await self.commit()
        await self.invalidate_reporting_cache()
        deal = await self.get_deal(deal.id)
        await realtime_manager.broadcast({"event": "deal.updated", "payload": {"id": str(deal.id), "title": deal.title}})
        return deal

    async def delete_deal(self, deal_id: UUID, *, actor_id: UUID):
        deal = await self.get_deal(deal_id)
        await self.repository.soft_delete(deal, actor_id)
        await self.commit()
        await self.invalidate_reporting_cache()
        await realtime_manager.broadcast({"event": "deal.deleted", "payload": {"id": str(deal.id)}})

    async def _ensure_customer(self, customer_id: UUID) -> None:
        customer = await self.customer_repository.get(customer_id)
        if customer is None:
            raise NotFoundError("Customer not found.")
