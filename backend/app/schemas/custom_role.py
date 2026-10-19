from datetime import datetime
from uuid import UUID

from pydantic import Field, field_validator

from app.core.permissions import PermissionCode
from app.schemas.common import ORMModel

LEAD_ACCESS_MAX_CAMPAIGNS = 200
LEAD_ACCESS_MAX_SOURCES = 50
LEAD_ACCESS_SOURCE_MAX_LEN = 100


class LeadAccess(ORMModel):
    """A role's "Data access": which leads its users see (and everything built from them). Every limit that is set
    must be met; a lead with no campaign (or no source) is outside a campaign (or source) limit."""

    own_leads_only: bool = False
    # None = every campaign; otherwise the chosen campaigns (ids from the tenant's campaign list).
    campaign_ids: list[UUID] | None = Field(default=None, max_length=LEAD_ACCESS_MAX_CAMPAIGNS)
    # None = every source; otherwise the chosen source labels (matched ignoring case and surrounding spaces).
    sources: list[str] | None = Field(default=None, max_length=LEAD_ACCESS_MAX_SOURCES)

    @field_validator("campaign_ids")
    @classmethod
    def _campaigns_chosen(cls, value: list[UUID] | None) -> list[UUID] | None:
        if value is None:
            return None
        unique = list(dict.fromkeys(value))
        if not unique:
            raise ValueError("Choose at least one campaign, or allow all campaigns.")
        return unique

    @field_validator("sources")
    @classmethod
    def _sources_chosen(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        seen: dict[str, str] = {}
        for raw in value:
            label = " ".join(str(raw or "").split())
            if not label:
                continue
            if len(label) > LEAD_ACCESS_SOURCE_MAX_LEN:
                raise ValueError(f"A source name can be at most {LEAD_ACCESS_SOURCE_MAX_LEN} characters.")
            seen.setdefault(label.lower(), label)
        if not seen:
            raise ValueError("Choose at least one source, or allow all sources.")
        return list(seen.values())

    @property
    def limited(self) -> bool:
        return self.own_leads_only or self.campaign_ids is not None or self.sources is not None


class LeadAccessCampaign(ORMModel):
    id: UUID
    name: str


class LeadAccessRead(ORMModel):
    own_leads_only: bool = False
    # None = every campaign / every source.
    campaigns: list[LeadAccessCampaign] | None = None
    sources: list[str] | None = None


class LeadAccessOptions(ORMModel):
    """What the role editor offers: the tenant's campaigns and the lead sources (standard + in use)."""

    campaigns: list[LeadAccessCampaign]
    sources: list[str]


class CustomRoleCreate(ORMModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    permissions: list[PermissionCode] = Field(default_factory=list)
    lead_access: LeadAccess = Field(default_factory=LeadAccess)


class CustomRoleUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    permissions: list[PermissionCode] | None = None
    is_active: bool | None = None
    # Left out = unchanged.
    lead_access: LeadAccess | None = None


class CustomRoleRead(ORMModel):
    id: UUID
    name: str
    description: str | None
    permissions: list[str]
    is_active: bool
    assigned_user_count: int = 0
    lead_access: LeadAccessRead = Field(default_factory=LeadAccessRead)
    created_at: datetime
    updated_at: datetime


class AssignCustomRoleRequest(ORMModel):
    custom_role_id: UUID


class UnassignCustomRoleRequest(ORMModel):
    new_role: str  # validated against ROLE_INDUSTRIES in the endpoint
