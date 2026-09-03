from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissions
from app.core.permissions import ASSIGNED_ONLY_LEAD_ROLES, PermissionCode
from app.database.session import get_db_session
from app.schemas.dashboard import DashboardChartsResponse, DashboardSummaryResponse, RecentActivitiesResponse
from app.services.dashboard import DashboardService


router = APIRouter()


@router.get("/summary", response_model=DashboardSummaryResponse)
async def summary(
    current_user=Depends(require_permissions(PermissionCode.DASHBOARD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    # Front-line reps see only their own assigned leads/tasks (mirrors the leads
    # list scoping); owner/managers keep the org-wide view.
    owner_id = current_user.id if current_user.role in ASSIGNED_ONLY_LEAD_ROLES else None
    return await DashboardService(session).get_summary(owner_id)


@router.get("/charts", response_model=DashboardChartsResponse)
async def charts(
    current_user=Depends(require_permissions(PermissionCode.DASHBOARD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    owner_id = current_user.id if current_user.role in ASSIGNED_ONLY_LEAD_ROLES else None
    return await DashboardService(session).get_charts(owner_id)


@router.get("/recent-activities", response_model=RecentActivitiesResponse)
async def recent_activities(
    _: object = Depends(require_permissions(PermissionCode.DASHBOARD_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    return await DashboardService(session).get_recent_activities()
