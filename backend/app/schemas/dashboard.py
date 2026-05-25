from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class DashboardSummaryResponse(BaseModel):
    total_customers: int
    active_leads: int
    open_deals_value: Decimal
    overdue_tasks: int
    recent_activity_count: int


class ChartPoint(BaseModel):
    label: str
    value: Decimal | int | float


class DashboardChartsResponse(BaseModel):
    revenue_trend: list[ChartPoint]
    lead_stage_breakdown: list[ChartPoint]
    task_status_breakdown: list[ChartPoint]


class RecentActivityItem(BaseModel):
    id: str
    customer_id: str
    customer_name: str
    type: str
    note: str
    created_at: datetime


class RecentActivitiesResponse(BaseModel):
    items: list[RecentActivityItem]
