from uuid import UUID

from app.core.exceptions import NotFoundError
from app.repositories.activities import ActivityRepository
from app.repositories.customers import CustomerRepository
from app.schemas.activity import ActivityCreate, ActivityFilterParams
from app.schemas.common import PaginationParams
from app.services.base import ServiceBase
from app.services.realtime import realtime_manager
from app.utils.query import validate_sort_field


class ActivityService(ServiceBase):
    allowed_sort_fields = {"created_at", "updated_at", "type"}

    def __init__(self, session):
        super().__init__(session)
        self.repository = ActivityRepository(session)
        self.customer_repository = CustomerRepository(session)

    async def list_activities(self, pagination: PaginationParams, filters: ActivityFilterParams):
        sort_by = validate_sort_field(filters.sort_by, self.allowed_sort_fields)
        return await self.repository.list(
            pagination=pagination,
            filters={
                "customer_id": filters.customer_id,
                "type": filters.type,
                "created_by_id": filters.created_by_id,
            },
            search=filters.search,
            search_fields=("note",),
            sort_by=sort_by,
            sort_order=filters.sort_order,
            options=self.repository.default_options,
        )

    async def create_activity(self, payload: ActivityCreate, *, actor_id: UUID):
        customer = await self.customer_repository.get(payload.customer_id)
        if customer is None:
            raise NotFoundError("Customer not found.")
        activity = await self.repository.create(
            {
                **payload.model_dump(),
                "created_by_id": actor_id,
                "updated_by_id": actor_id,
            }
        )
        await self.commit()
        await self.invalidate_reporting_cache()
        activity = await self.repository.get(activity.id, options=self.repository.default_options)
        await realtime_manager.broadcast(
            {"event": "activity.created", "payload": {"id": str(activity.id), "customer_id": str(activity.customer_id)}}
        )
        return activity
