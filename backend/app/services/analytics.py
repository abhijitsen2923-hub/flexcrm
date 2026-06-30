from app.core.cache import cache_client
from app.core.config import get_settings
from app.core.tenancy import get_schema
from app.repositories.analytics import AnalyticsRepository
from app.repositories.dashboard import DashboardRepository
from app.schemas.analytics import (
    AnalyticsConversionResponse,
    AnalyticsLeadsResponse,
    AnalyticsRevenueResponse,
)
from app.schemas.dashboard import ChartPoint


class AnalyticsService:
    def __init__(self, session):
        self.session = session
        self.repository = AnalyticsRepository(session)
        self.dashboard_repository = DashboardRepository(session)
        self.cache_ttl = get_settings().cache_ttl_seconds

    def _cache_key(self, name: str) -> str:
        # Scope by tenant schema so cached analytics never cross tenants (shared Redis).
        scope = get_schema(self.session) or "public"
        return f"analytics:{name}:{scope}"

    async def _read_cache(self, cache_key: str, model_cls):
        """Validated model from cache, or None on miss / stale entry (recompute)."""
        cached = await cache_client.get_json(cache_key)
        if not cached:
            return None
        try:
            return model_cls(**cached)
        except Exception:
            await cache_client.delete(cache_key)
            return None

    async def get_revenue(self) -> AnalyticsRevenueResponse:
        cache_key = self._cache_key("revenue")
        cached = await self._read_cache(cache_key, AnalyticsRevenueResponse)
        if cached is not None:
            return cached

        monthly_revenue = [
            ChartPoint(label=label, value=value) for label, value in await self.dashboard_repository.revenue_trend()
        ]
        response = AnalyticsRevenueResponse(
            total_closed_revenue=await self.repository.closed_revenue(),
            open_pipeline_value=await self.repository.open_pipeline_value(),
            monthly_revenue=monthly_revenue,
        )
        await cache_client.set_json(cache_key, response.model_dump(mode="json"), self.cache_ttl)
        return response

    async def get_leads(self) -> AnalyticsLeadsResponse:
        cache_key = self._cache_key("leads")
        cached = await self._read_cache(cache_key, AnalyticsLeadsResponse)
        if cached is not None:
            return cached

        response = AnalyticsLeadsResponse(
            total_leads=await self.repository.total_leads(),
            won_leads=await self.repository.won_leads(),
            stage_breakdown=[
                ChartPoint(label=label, value=value) for label, value in await self.repository.lead_stage_breakdown()
            ],
            source_breakdown=[
                ChartPoint(label=label, value=value) for label, value in await self.repository.source_breakdown()
            ],
        )
        await cache_client.set_json(cache_key, response.model_dump(mode="json"), self.cache_ttl)
        return response

    async def get_conversion(self) -> AnalyticsConversionResponse:
        cache_key = self._cache_key("conversion")
        cached = await self._read_cache(cache_key, AnalyticsConversionResponse)
        if cached is not None:
            return cached

        total_leads = await self.repository.total_leads()
        won_leads = await self.repository.won_leads()
        won_deals, total_deals = await self.repository.deal_counts()
        response = AnalyticsConversionResponse(
            lead_to_win_rate=(won_leads / total_leads * 100) if total_leads else 0,
            deal_win_rate=(won_deals / total_deals * 100) if total_deals else 0,
            average_probability=await self.repository.average_lead_probability(),
        )
        await cache_client.set_json(cache_key, response.model_dump(mode="json"), self.cache_ttl)
        return response
