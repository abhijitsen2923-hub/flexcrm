"""Custom role CRUD + user assignment endpoints.

Custom roles are org-scoped named permission templates. Org admins can define
any combination of the 23 PermissionCodes as a role, give it a name, and
assign it to one or more users. A user with role="custom" sources their base
permissions from the linked CustomRole template; UserPermissionGrant still
works as additive overrides on top.

All endpoints require USER_MANAGE.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_permissions
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.permissions import PermissionCode, role_is_valid_for_industry
from app.core.tenancy import current_org
from app.database.enums import UserRole
from app.database.session import get_db_session
from app.models.custom_role import CustomRole, UserCustomRoleAssignment
from app.models.organization import Organization
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.custom_role import (
    AssignCustomRoleRequest,
    CustomRoleCreate,
    CustomRoleRead,
    CustomRoleUpdate,
    UnassignCustomRoleRequest,
)
from app.services.users import UserService

router = APIRouter()


async def _get_custom_role_or_404(role_id: UUID, session: AsyncSession) -> CustomRole:
    role = (
        await session.execute(select(CustomRole).where(CustomRole.id == role_id))
    ).scalar_one_or_none()
    if not role:
        raise NotFoundError("Custom role not found.")
    return role


@router.get("/custom-roles", response_model=list[CustomRoleRead])
async def list_custom_roles(
    _: object = Depends(require_permissions(PermissionCode.USER_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    roles = (await session.execute(select(CustomRole).order_by(CustomRole.name))).scalars().all()
    result = []
    for role in roles:
        count = (
            await session.execute(
                select(func.count()).where(UserCustomRoleAssignment.custom_role_id == role.id)
            )
        ).scalar_one()
        result.append(
            CustomRoleRead.model_validate(role).model_copy(update={"assigned_user_count": count})
        )
    return result


@router.post("/custom-roles", response_model=CustomRoleRead, status_code=status.HTTP_201_CREATED)
async def create_custom_role(
    payload: CustomRoleCreate,
    current_user=Depends(require_permissions(PermissionCode.USER_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    existing = (
        await session.execute(select(CustomRole).where(CustomRole.name == payload.name))
    ).scalar_one_or_none()
    if existing:
        raise ConflictError(f"A custom role named '{payload.name}' already exists.")

    role = CustomRole(
        name=payload.name,
        description=payload.description,
        permissions=[p.value for p in payload.permissions],
        created_by_id=current_user.id,
        updated_by_id=current_user.id,
    )
    session.add(role)
    await session.commit()
    await session.refresh(role)
    return CustomRoleRead.model_validate(role).model_copy(update={"assigned_user_count": 0})


@router.get("/custom-roles/{role_id}", response_model=CustomRoleRead)
async def get_custom_role(
    role_id: UUID,
    _: object = Depends(require_permissions(PermissionCode.USER_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    role = await _get_custom_role_or_404(role_id, session)
    count = (
        await session.execute(
            select(func.count()).where(UserCustomRoleAssignment.custom_role_id == role_id)
        )
    ).scalar_one()
    return CustomRoleRead.model_validate(role).model_copy(update={"assigned_user_count": count})


@router.put("/custom-roles/{role_id}", response_model=CustomRoleRead)
async def update_custom_role(
    role_id: UUID,
    payload: CustomRoleUpdate,
    current_user=Depends(require_permissions(PermissionCode.USER_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    role = await _get_custom_role_or_404(role_id, session)
    update_data = payload.model_dump(exclude_unset=True)

    if "name" in update_data and update_data["name"] != role.name:
        clash = (
            await session.execute(
                select(CustomRole).where(CustomRole.name == update_data["name"])
            )
        ).scalar_one_or_none()
        if clash:
            raise ConflictError(f"A custom role named '{update_data['name']}' already exists.")
        role.name = update_data["name"]

    if "description" in update_data:
        role.description = update_data["description"]
    if "is_active" in update_data:
        role.is_active = update_data["is_active"]
    if "permissions" in update_data:
        role.permissions = [p.value for p in update_data["permissions"]]

    role.updated_by_id = current_user.id
    await session.commit()
    await session.refresh(role)

    count = (
        await session.execute(
            select(func.count()).where(UserCustomRoleAssignment.custom_role_id == role_id)
        )
    ).scalar_one()
    return CustomRoleRead.model_validate(role).model_copy(update={"assigned_user_count": count})


@router.delete("/custom-roles/{role_id}", response_model=MessageResponse)
async def delete_custom_role(
    role_id: UUID,
    _: object = Depends(require_permissions(PermissionCode.USER_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    role = await _get_custom_role_or_404(role_id, session)
    count = (
        await session.execute(
            select(func.count()).where(UserCustomRoleAssignment.custom_role_id == role_id)
        )
    ).scalar_one()
    if count > 0:
        raise ConflictError(
            f"Cannot delete: {count} user(s) are assigned to this role. "
            "Reassign them first."
        )
    await session.delete(role)
    await session.commit()
    return MessageResponse(message="Custom role deleted.")


@router.post("/users/{user_id}/custom-role", response_model=MessageResponse)
async def assign_custom_role(
    user_id: UUID,
    payload: AssignCustomRoleRequest,
    current_user=Depends(require_permissions(PermissionCode.USER_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    """Assign a custom role to a user.

    Sets user.role = "custom" and creates/replaces the UserCustomRoleAssignment.
    Any existing predefined role and per-user grants are preserved; the custom
    role permissions become the new base set.
    """
    target = await UserService(session).get_user(user_id)
    if not target:
        raise NotFoundError("User not found.")

    role_template = await _get_custom_role_or_404(payload.custom_role_id, session)
    if not role_template.is_active:
        raise ValidationError("This custom role is inactive and cannot be assigned.")

    # Upsert assignment
    existing_assignment = (
        await session.execute(
            select(UserCustomRoleAssignment).where(UserCustomRoleAssignment.user_id == user_id)
        )
    ).scalar_one_or_none()

    if existing_assignment:
        existing_assignment.custom_role_id = payload.custom_role_id
    else:
        session.add(UserCustomRoleAssignment(
            user_id=user_id,
            custom_role_id=payload.custom_role_id,
        ))

    # Set the sentinel role
    target.role = UserRole.custom
    target.updated_by_id = current_user.id
    await session.commit()
    return MessageResponse(message=f"Custom role '{role_template.name}' assigned.")


@router.delete("/users/{user_id}/custom-role", response_model=MessageResponse)
async def unassign_custom_role(
    user_id: UUID,
    payload: UnassignCustomRoleRequest,
    current_user=Depends(require_permissions(PermissionCode.USER_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    """Remove a user's custom role and reset them to a predefined role.

    Requires `new_role` in the request body — the predefined role to fall back to.
    """
    target = await UserService(session).get_user(user_id)
    if not target:
        raise NotFoundError("User not found.")

    try:
        new_role = UserRole(payload.new_role)
    except ValueError:
        raise ValidationError(f"'{payload.new_role}' is not a valid role.")

    # Validate new_role is a real predefined role (not legacy, not custom)
    org_id = current_org(session)
    org = (
        await session.execute(select(Organization).where(Organization.id == org_id))
    ).scalar_one_or_none() if org_id else None
    industry = org.business_type if org else None

    if not role_is_valid_for_industry(new_role, industry) or new_role == UserRole.custom:
        raise ValidationError(
            f"Role '{new_role.value}' is not valid for this organisation."
        )

    assignment = (
        await session.execute(
            select(UserCustomRoleAssignment).where(UserCustomRoleAssignment.user_id == user_id)
        )
    ).scalar_one_or_none()
    if assignment:
        await session.delete(assignment)

    target.role = new_role
    target.updated_by_id = current_user.id
    await session.commit()
    return MessageResponse(message=f"Custom role removed. User reset to '{new_role.value}'.")
