from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.core.permissions import PermissionCode
from app.schemas.common import ORMModel


class CustomRoleCreate(ORMModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    permissions: list[PermissionCode] = Field(default_factory=list)


class CustomRoleUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    permissions: list[PermissionCode] | None = None
    is_active: bool | None = None


class CustomRoleRead(ORMModel):
    id: UUID
    name: str
    description: str | None
    permissions: list[str]
    is_active: bool
    assigned_user_count: int = 0
    created_at: datetime
    updated_at: datetime


class AssignCustomRoleRequest(ORMModel):
    custom_role_id: UUID


class UnassignCustomRoleRequest(ORMModel):
    new_role: str  # validated against ROLE_INDUSTRIES in the endpoint
