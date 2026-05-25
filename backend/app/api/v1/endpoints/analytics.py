from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissions
from app.core.permissions import PermissionCode
from app.database.session import get_db_session
from app.schemas.analytics import AnalyticsConversionResponse, AnalyticsLeadsResponse, AnalyticsRevenueResponse
from app.services.analytics import AnalyticsService


router = APIRouter()


@router.get("/revenue", response_model=AnalyticsRevenueResponse)
async def revenue(
    _: object = Depends(require_permissions(PermissionCode.ANALYTICS_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    return await AnalyticsService(session).get_revenue()


@router.get("/leads", response_model=AnalyticsLeadsResponse)
async def leads(
    _: object = Depends(require_permissions(PermissionCode.ANALYTICS_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    return await AnalyticsService(session).get_leads()


@router.get("/conversion", response_model=AnalyticsConversionResponse)
async def conversion(
    _: object = Depends(require_permissions(PermissionCode.ANALYTICS_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    return await AnalyticsService(session).get_conversion()
