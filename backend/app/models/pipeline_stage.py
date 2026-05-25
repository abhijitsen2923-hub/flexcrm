from sqlalchemy import CheckConstraint, Enum, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.enums import LeadIndustry, PipelineStageCategory
from app.models.base import UUIDPrimaryKeyMixin


class PipelineStage(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "pipeline_stages"
    __table_args__ = (
        UniqueConstraint("industry", "code", name="uq_pipeline_stages_industry_code"),
        UniqueConstraint("industry", "position", name="uq_pipeline_stages_industry_position"),
        CheckConstraint("position >= 1 AND position <= 15", name="ck_pipeline_stages_position_range"),
    )

    industry: Mapped[LeadIndustry] = mapped_column(
        Enum(LeadIndustry, name="lead_industry_enum"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[PipelineStageCategory] = mapped_column(
        Enum(PipelineStageCategory, name="pipeline_stage_category_enum"), nullable=False
    )
    comment_required: Mapped[bool] = mapped_column(nullable=False, default=True)
