from decimal import Decimal

from app.core.cache import cache_client
from app.core.config import get_settings
from app.repositories.dashboard import DashboardRepository
from app.schemas.dashboard import (
    ChartPoint,
    DashboardChartsResponse,
    DashboardSummaryResponse,
    RecentActivitiesResponse,
    RecentActivityItem,
)


class DashboardService:
    def __init__(self, session):
        self.repository = DashboardRepository(session)
        self.cache_ttl = get_settings().cache_ttl_seconds

    async def get_summary(self) -> DashboardSummaryResponse:
        cache_key = "dashboard:summary"
        cached = await cache_client.get_json(cache_key)
        if cached:
            return DashboardSummaryResponse(**cached)

        summary = DashboardSummaryResponse(**await self.repository.summary())
        await cache_client.set_json(cache_key, summary.model_dump(mode="json"), self.cache_ttl)
        return summary

    async def get_charts(self) -> DashboardChartsResponse:
        cache_key = "dashboard:charts"
        cached = await cache_client.get_json(cache_key)
        if cached:
            return DashboardChartsResponse(**cached)

        revenue_trend = [ChartPoint(label=label, value=Decimal(value)) for label, value in await self.repository.revenue_trend()]
        lead_stage_breakdown = [ChartPoint(label=label, value=value) for label, value in await self.repository.lead_stage_breakdown()]
        task_status_breakdown = [ChartPoint(label=label, value=value) for label, value in await self.repository.task_status_breakdown()]
        response = DashboardChartsResponse(
            revenue_trend=revenue_trend,
            lead_stage_breakdown=lead_stage_breakdown,
            task_status_breakdown=task_status_breakdown,
        )
        await cache_client.set_json(cache_key, response.model_dump(mode="json"), self.cache_ttl)
        return response

    async def get_recent_activities(self) -> RecentActivitiesResponse:
        cache_key = "dashboard:recent-activities"
        cached = await cache_client.get_json(cache_key)
        if cached:
            return RecentActivitiesResponse(**cached)

        rows = await self.repository.recent_activities()
        response = RecentActivitiesResponse(
            items=[
                RecentActivityItem(
                    id=str(activity_id),
                    customer_id=str(customer_id),
                    customer_name=customer_name,
                    type=activity_type.value,
                    note=note,
                    created_at=created_at,
                )
                for activity_id, customer_id, customer_name, activity_type, note, created_at in rows
            ]
        )
        await cache_client.set_json(cache_key, response.model_dump(mode="json"), self.cache_ttl)
        return response
