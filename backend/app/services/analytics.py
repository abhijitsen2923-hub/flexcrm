from app.core.cache import cache_client
from app.core.config import get_settings
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
        self.repository = AnalyticsRepository(session)
        self.dashboard_repository = DashboardRepository(session)
        self.cache_ttl = get_settings().cache_ttl_seconds

    async def get_revenue(self) -> AnalyticsRevenueResponse:
        cache_key = "analytics:revenue"
        cached = await cache_client.get_json(cache_key)
        if cached:
            return AnalyticsRevenueResponse(**cached)

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
        cache_key = "analytics:leads"
        cached = await cache_client.get_json(cache_key)
        if cached:
            return AnalyticsLeadsResponse(**cached)

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
        cache_key = "analytics:conversion"
        cached = await cache_client.get_json(cache_key)
        if cached:
            return AnalyticsConversionResponse(**cached)

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
