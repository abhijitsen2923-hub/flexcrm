from uuid import UUID

from app.database.enums import LeadIndustry, PipelineStageCategory
from app.schemas.common import ORMModel


class PipelineStageRead(ORMModel):
    id: UUID
    industry: LeadIndustry
    position: int
    code: str
    name: str
    category: PipelineStageCategory
    comment_required: bool
