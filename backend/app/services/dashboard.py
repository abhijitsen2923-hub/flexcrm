from decimal import Decimal

from app.core.cache import cache_client
from app.core.config import get_settings
from app.core.tenancy import get_schema
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
        self.session = session
        self.repository = DashboardRepository(session)
        self.cache_ttl = get_settings().cache_ttl_seconds

    def _cache_key(self, name: str) -> str:
        # Scope by tenant schema so one tenant's cached dashboard is never served
        # to another (shared Redis). Falls back to "public" when no schema is set.
        scope = get_schema(self.session) or "public"
        return f"dashboard:{name}:{scope}"

    async def _read_cache(self, cache_key: str, model_cls):
        """Return a validated model from cache, or None on miss / stale entry.

        A cached value that no longer matches the schema (e.g. left over from an
        older deploy) must not 500 the request — drop it and recompute."""
        cached = await cache_client.get_json(cache_key)
        if not cached:
            return None
        try:
            return model_cls(**cached)
        except Exception:
            await cache_client.delete(cache_key)
            return None

    async def get_summary(self) -> DashboardSummaryResponse:
        cache_key = self._cache_key("summary")
        cached = await self._read_cache(cache_key, DashboardSummaryResponse)
        if cached is not None:
            return cached

        summary = DashboardSummaryResponse(**await self.repository.summary())
        await cache_client.set_json(cache_key, summary.model_dump(mode="json"), self.cache_ttl)
        return summary

    async def get_charts(self) -> DashboardChartsResponse:
        cache_key = self._cache_key("charts")
        cached = await self._read_cache(cache_key, DashboardChartsResponse)
        if cached is not None:
            return cached

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
        cache_key = self._cache_key("recent-activities")
        cached = await self._read_cache(cache_key, RecentActivitiesResponse)
        if cached is not None:
            return cached

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
