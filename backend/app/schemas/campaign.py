from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.common import ORMModel


class CampaignOption(ORMModel):
    """A campaign as the New Lead form / filter list it."""

    id: UUID
    name: str
    is_active: bool
    needs_review: bool


class CampaignAliasRead(ORMModel):
    id: UUID
    alias: str
    kind: str
    created_at: datetime


class CampaignRead(ORMModel):
    id: UUID
    name: str
    is_active: bool
    needs_review: bool
    source: str
    lead_count: int
    aliases: list[CampaignAliasRead]
    created_at: datetime
    updated_at: datetime


class CampaignSuggestion(ORMModel):
    keep_id: UUID
    merge_id: UUID
    reason: Literal["spacing_punctuation", "similar"]


class CampaignOverview(ORMModel):
    items: list[CampaignRead]
    suggestions: list[CampaignSuggestion]


class CampaignCreate(ORMModel):
    name: str = Field(min_length=1, max_length=120)


class CampaignRename(ORMModel):
    name: str = Field(min_length=1, max_length=120)


class CampaignUpdate(ORMModel):
    is_active: bool | None = None
    # Only "mark reviewed" (False) is accepted — a manager can't flag a campaign back to needs-review.
    needs_review: Literal[False] | None = None


class CampaignMerge(ORMModel):
    source_ids: list[UUID] = Field(min_length=1, max_length=50)
    target_id: UUID


class CampaignMutationResult(ORMModel):
    campaign: CampaignRead | None = None
    leads_updated: int = 0
