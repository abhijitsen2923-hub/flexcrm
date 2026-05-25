from app.schemas.activity import ActivityCreate, ActivityFilterParams, ActivityRead
from app.schemas.analytics import (
    AnalyticsConversionResponse,
    AnalyticsLeadsResponse,
    AnalyticsRevenueResponse,
)
from app.schemas.auth import LoginRequest, LogoutRequest, RefreshTokenRequest, RegisterRequest, TokenResponse
from app.schemas.common import MessageResponse, PageMeta, PaginatedResponse, PaginationParams
from app.schemas.customer import CustomerCreate, CustomerFilterParams, CustomerRead, CustomerUpdate
from app.schemas.dashboard import (
    DashboardChartsResponse,
    DashboardSummaryResponse,
    RecentActivitiesResponse,
)
from app.schemas.deal import DealCreate, DealFilterParams, DealRead, DealUpdate
from app.schemas.lead import LeadCreate, LeadFilterParams, LeadRead, LeadUpdate
from app.schemas.task import TaskCreate, TaskFilterParams, TaskRead, TaskUpdate
from app.schemas.user import UserCreate, UserFilterParams, UserRead, UserSummary, UserUpdate

__all__ = [
    "ActivityCreate",
    "ActivityFilterParams",
    "ActivityRead",
    "AnalyticsConversionResponse",
    "AnalyticsLeadsResponse",
    "AnalyticsRevenueResponse",
    "LoginRequest",
    "LogoutRequest",
    "RefreshTokenRequest",
    "RegisterRequest",
    "TokenResponse",
    "MessageResponse",
    "PageMeta",
    "PaginatedResponse",
    "PaginationParams",
    "CustomerCreate",
    "CustomerFilterParams",
    "CustomerRead",
    "CustomerUpdate",
    "DashboardChartsResponse",
    "DashboardSummaryResponse",
    "RecentActivitiesResponse",
    "DealCreate",
    "DealFilterParams",
    "DealRead",
    "DealUpdate",
    "LeadCreate",
    "LeadFilterParams",
    "LeadRead",
    "LeadUpdate",
    "TaskCreate",
    "TaskFilterParams",
    "TaskRead",
    "TaskUpdate",
    "UserCreate",
    "UserFilterParams",
    "UserRead",
    "UserSummary",
    "UserUpdate",
]
