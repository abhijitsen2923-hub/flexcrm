from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.database.enums import LeadIndustry
from app.schemas.common import ORMModel


class OrganizationRead(ORMModel):
    id: UUID
    name: str
    business_type: LeadIndustry
    plan: str
    features: dict | None = None
    # Computed at response time — ISO 4217 codes the org may use.
    allowed_currencies: list[str] = []
    created_at: datetime
    updated_at: datetime


class OrganizationUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    plan: str | None = Field(default=None, max_length=32)
    features: dict | None = None
