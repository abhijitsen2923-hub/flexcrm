from uuid import UUID

from app.core.exceptions import NotFoundError
from app.repositories.customers import CustomerRepository
from app.schemas.common import PaginationParams
from app.schemas.customer import CustomerCreate, CustomerFilterParams, CustomerUpdate
from app.services.base import ServiceBase
from app.services.realtime import realtime_manager
from app.utils.query import validate_sort_field


class CustomerService(ServiceBase):
    allowed_sort_fields = {"created_at", "updated_at", "company_name", "contact_name", "status", "source"}

    def __init__(self, session):
        super().__init__(session)
        self.repository = CustomerRepository(session)

    async def list_customers(self, pagination: PaginationParams, filters: CustomerFilterParams):
        sort_by = validate_sort_field(filters.sort_by, self.allowed_sort_fields)
        return await self.repository.list(
            pagination=pagination,
            filters={
                "status": filters.status,
                "source": filters.source,
                "created_by_id": filters.created_by_id,
            },
            search=filters.search,
            search_fields=("company_name", "contact_name", "email", "phone", "address"),
            sort_by=sort_by,
            sort_order=filters.sort_order,
        )

    async def get_customer(self, customer_id: UUID):
        customer = await self.repository.get(customer_id)
        if customer is None:
            raise NotFoundError("Customer not found.")
        return customer

    async def create_customer(self, payload: CustomerCreate, *, actor_id: UUID):
        customer = await self.repository.create(
            {
                **payload.model_dump(),
                "created_by_id": actor_id,
                "updated_by_id": actor_id,
            }
        )
        await self.commit()
        await self.invalidate_reporting_cache()
        await realtime_manager.broadcast(
            {"event": "customer.created", "payload": {"id": str(customer.id), "company_name": customer.company_name}}
        )
        return customer

    async def update_customer(self, customer_id: UUID, payload: CustomerUpdate, *, actor_id: UUID):
        customer = await self.get_customer(customer_id)
        update_data = payload.model_dump(exclude_unset=True)
        update_data["updated_by_id"] = actor_id
        customer = await self.repository.update(customer, update_data)
        await self.commit()
        await self.invalidate_reporting_cache()
        await realtime_manager.broadcast(
            {"event": "customer.updated", "payload": {"id": str(customer.id), "company_name": customer.company_name}}
        )
        return customer

    async def delete_customer(self, customer_id: UUID, *, actor_id: UUID):
        customer = await self.get_customer(customer_id)
        await self.repository.soft_delete(customer, actor_id)
        await self.commit()
        await self.invalidate_reporting_cache()
        await realtime_manager.broadcast({"event": "customer.deleted", "payload": {"id": str(customer.id)}})
