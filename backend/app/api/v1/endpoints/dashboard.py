from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissions
from app.core.permissions import PermissionCode
from app.database.session import get_db_session
from app.schemas.dashboard import DashboardChartsResponse, DashboardSummaryResponse, RecentActivitiesResponse
from app.services.dashboard import DashboardService


router = APIRouter()


@router.get("/summary", response_model=DashboardSummaryResponse)
async def summary(
    _: object = Depends(require_permissions(PermissionCode.DASHBOARD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    return await DashboardService(session).get_summary()


@router.get("/charts", response_model=DashboardChartsResponse)
async def charts(
    _: object = Depends(require_permissions(PermissionCode.DASHBOARD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    return await DashboardService(session).get_charts()


@router.get("/recent-activities", response_model=RecentActivitiesResponse)
async def recent_activities(
    _: object = Depends(require_permissions(PermissionCode.DASHBOARD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    return await DashboardService(session).get_recent_activities()
