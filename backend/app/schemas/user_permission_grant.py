"""Schemas for explicit permission grants (Phase 8).

`UserPermissionGrant` rows are additive overrides on top of role defaults —
admin layers `FINANCE_REFUND` onto a counselor without changing the role.
"""
from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.core.permissions import PermissionCode
from app.schemas.common import ORMModel


class GrantedPermissionRead(ORMModel):
    id: UUID
    user_id: UUID
    permission_code: str
    granted_by_id: UUID | None = None
    created_at: datetime


class GrantPermissionRequest(ORMModel):
    permission_code: PermissionCode = Field(
        description="The fine- or coarse-grained code to grant. Coarse codes auto-imply finer ones.",
    )


class UserPermissionsRead(ORMModel):
    """Returned by `GET /users/{id}/permissions` and `GET /me/permissions`.

    `effective` is what gates calls — `defaults` and `granted` are shown side-by-side
    in the admin drawer so the UI can render role-default checkboxes as disabled
    (cannot be revoked without changing the role) and grant rows as toggleable.
    """
    user_id: UUID
    role_defaults: list[str]
    granted: list[GrantedPermissionRead]
    effective: list[str]
