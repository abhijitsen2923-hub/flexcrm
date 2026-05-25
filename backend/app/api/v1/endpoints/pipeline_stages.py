from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database.session import get_db_session
from app.repositories.pipeline_stages import PipelineStageRepository
from app.schemas.pipeline_stage import PipelineStageRead


router = APIRouter()


@router.get("", response_model=list[PipelineStageRead])
async def list_pipeline_stages(
    _: object = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Return all 30 pipeline stages (Education + Travel), ordered by position.

    Cheap, static reference data — the frontend caches once per session.
    """
    return await PipelineStageRepository(session).all_stages()
