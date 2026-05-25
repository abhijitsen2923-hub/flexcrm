from decimal import Decimal

from pydantic import BaseModel

from app.schemas.dashboard import ChartPoint


class AnalyticsRevenueResponse(BaseModel):
    total_closed_revenue: Decimal
    open_pipeline_value: Decimal
    monthly_revenue: list[ChartPoint]


class AnalyticsLeadsResponse(BaseModel):
    total_leads: int
    won_leads: int
    stage_breakdown: list[ChartPoint]
    source_breakdown: list[ChartPoint]


class AnalyticsConversionResponse(BaseModel):
    lead_to_win_rate: float
    deal_win_rate: float
    average_probability: float
