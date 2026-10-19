"""Custom role CRUD + user assignment endpoints.

Custom roles are org-scoped named permission templates. Org admins can define
any combination of the PermissionCodes as a role, give it a name, and
assign it to one or more users. A user with role="custom" sources their base
permissions from the linked CustomRole template; UserPermissionGrant still
works as additive overrides on top.

A role can also limit which leads its users see ("Data access": chosen
campaigns, chosen sources, only the leads assigned to them) — enforced by
app/services/lead_scope.py.

All endpoints require USER_MANAGE. Nobody gives out more than they hold: a
role's permissions (and the built-in role a user falls back to) must be ones the
caller holds, and nobody changes their own role here.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ensure_caller_holds, require_permissions
from app.core.exceptions import AuthorizationError, ConflictError, NotFoundError, ValidationError
from app.core.lead_normalize import SOURCE_LABELS
from app.core.permissions import (
    LEAD_LIMITED_EXCLUDED,
    ROLE_PERMISSION_DEFAULTS,
    PermissionCode,
    role_is_valid_for_industry,
)
from app.core.tenancy import current_org
from app.database.enums import UserRole
from app.database.session import get_db_session
from app.models.campaign import Campaign
from app.models.custom_role import CustomRole, UserCustomRoleAssignment
from app.models.lead import Lead
from app.models.organization import Organization
from app.schemas.common import MessageResponse
from app.schemas.custom_role import (
    AssignCustomRoleRequest,
    CustomRoleCreate,
    CustomRoleRead,
    CustomRoleUpdate,
    LeadAccess,
    LeadAccessCampaign,
    LeadAccessOptions,
    LeadAccessRead,
    UnassignCustomRoleRequest,
)
from app.services.users import UserService

router = APIRouter()

_PERMISSION_LABELS = {
    PermissionCode.USER_MANAGE: "Manage users",
    PermissionCode.ORG_MANAGE: "Manage workspace",
    PermissionCode.CAMPAIGN_MANAGE: "Manage campaigns",
}


async def _get_custom_role_or_404(role_id: UUID, session: AsyncSession) -> CustomRole:
    role = (
        await session.execute(select(CustomRole).where(CustomRole.id == role_id))
    ).scalar_one_or_none()
    if not role:
        raise NotFoundError("Custom role not found.")
    return role


async def _assigned_counts(session: AsyncSession, role_ids: list[UUID]) -> dict[UUID, int]:
    if not role_ids:
        return {}
    rows = await session.execute(
        select(UserCustomRoleAssignment.custom_role_id, func.count())
        .where(UserCustomRoleAssignment.custom_role_id.in_(role_ids))
        .group_by(UserCustomRoleAssignment.custom_role_id)
    )
    return {role_id: count for role_id, count in rows}


async def _campaign_names(session: AsyncSession, ids: set[UUID]) -> dict[UUID, str]:
    if not ids:
        return {}
    rows = await session.execute(select(Campaign.id, Campaign.name).where(Campaign.id.in_(ids)))
    return {campaign_id: name for campaign_id, name in rows}


def _stored_campaign_ids(role: CustomRole) -> list[UUID]:
    out: list[UUID] = []
    for value in role.lead_campaign_ids or []:
        try:
            out.append(UUID(str(value)))
        except (TypeError, ValueError):
            continue
    return out


def _lead_access_read(role: CustomRole, names: dict[UUID, str]) -> LeadAccessRead:
    campaigns = None
    if role.lead_campaign_ids is not None:
        # A campaign removed since (cleared) no longer shows — and no longer matches any lead.
        campaigns = sorted(
            (LeadAccessCampaign(id=cid, name=names[cid]) for cid in _stored_campaign_ids(role) if cid in names),
            key=lambda c: c.name.lower(),
        )
    return LeadAccessRead(
        own_leads_only=bool(role.lead_own_only),
        campaigns=campaigns,
        sources=list(role.lead_sources) if role.lead_sources is not None else None,
    )


async def _role_reads(session: AsyncSession, roles: list[CustomRole]) -> list[CustomRoleRead]:
    counts = await _assigned_counts(session, [r.id for r in roles])
    names = await _campaign_names(session, {cid for r in roles for cid in _stored_campaign_ids(r)})
    return [
        CustomRoleRead.model_validate(role).model_copy(
            update={"assigned_user_count": counts.get(role.id, 0), "lead_access": _lead_access_read(role, names)}
        )
        for role in roles
    ]


async def _role_read(session: AsyncSession, role: CustomRole) -> CustomRoleRead:
    return (await _role_reads(session, [role]))[0]


def _check_limits_fit(permissions: list[str], access: LeadAccess) -> None:
    """A role limited to some leads can't manage users, the workspace or the campaign list (they act on every lead
    and could lift the limits)."""
    if not access.limited:
        return
    clash = [code for code in LEAD_LIMITED_EXCLUDED if code.value in set(permissions)]
    if clash:
        labels = ", ".join(sorted(_PERMISSION_LABELS.get(code, code.value) for code in clash))
        raise ValidationError(
            f"A role that sees only some leads can't also have: {labels}. Turn those off, or allow all leads."
        )


async def _check_campaigns_exist(session: AsyncSession, access: LeadAccess) -> None:
    if access.campaign_ids is None:
        return
    found = await _campaign_names(session, set(access.campaign_ids))
    if len(found) != len(set(access.campaign_ids)):
        raise ValidationError("Some chosen campaigns no longer exist — reopen the role and choose again.")


def _apply_lead_access(role: CustomRole, access: LeadAccess) -> None:
    role.lead_own_only = access.own_leads_only
    role.lead_campaign_ids = [str(cid) for cid in access.campaign_ids] if access.campaign_ids is not None else None
    role.lead_sources = list(access.sources) if access.sources is not None else None


def _current_access(role: CustomRole) -> LeadAccess:
    return LeadAccess.model_construct(
        own_leads_only=bool(role.lead_own_only),
        campaign_ids=_stored_campaign_ids(role) if role.lead_campaign_ids is not None else None,
        sources=list(role.lead_sources) if role.lead_sources is not None else None,
    )


@router.get("/custom-roles", response_model=list[CustomRoleRead])
async def list_custom_roles(
    _: object = Depends(require_permissions(PermissionCode.USER_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    roles = list((await session.execute(select(CustomRole).order_by(CustomRole.name))).scalars().all())
    return await _role_reads(session, roles)


@router.get("/custom-roles/lead-access-options", response_model=LeadAccessOptions)
async def lead_access_options(
    _: object = Depends(require_permissions(PermissionCode.USER_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    """What a role's "Data access" can be limited to: the tenant's campaigns and the lead sources (the standard list
    plus every other source on the tenant's leads). Declared before `/custom-roles/{role_id}`."""
    campaigns = (await session.execute(select(Campaign.id, Campaign.name))).all()
    in_use = (
        await session.execute(
            select(Lead.source).where(Lead.is_deleted.is_(False), Lead.source.is_not(None)).distinct()
        )
    ).scalars()
    sources: dict[str, str] = {label.lower(): label for label in SOURCE_LABELS}
    for value in in_use:
        label = " ".join(str(value or "").split())
        if label:
            sources.setdefault(label.lower(), label)
    return LeadAccessOptions(
        campaigns=sorted((LeadAccessCampaign(id=cid, name=name) for cid, name in campaigns), key=lambda c: c.name.lower()),
        sources=sorted(sources.values(), key=str.lower),
    )


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

    permissions = [p.value for p in payload.permissions]
    await ensure_caller_holds(session, current_user, permissions)
    _check_limits_fit(permissions, payload.lead_access)
    await _check_campaigns_exist(session, payload.lead_access)

    role = CustomRole(
        name=payload.name,
        description=payload.description,
        permissions=permissions,
        created_by_id=current_user.id,
        updated_by_id=current_user.id,
    )
    _apply_lead_access(role, payload.lead_access)
    session.add(role)
    await session.commit()
    await session.refresh(role)
    return await _role_read(session, role)


@router.get("/custom-roles/{role_id}", response_model=CustomRoleRead)
async def get_custom_role(
    role_id: UUID,
    _: object = Depends(require_permissions(PermissionCode.USER_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    role = await _get_custom_role_or_404(role_id, session)
    return await _role_read(session, role)


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

    permissions = (
        [p.value for p in payload.permissions] if payload.permissions is not None else list(role.permissions or [])
    )
    access = payload.lead_access if payload.lead_access is not None else _current_access(role)
    if payload.permissions is not None:
        await ensure_caller_holds(session, current_user, permissions)
    # Checked on the role as it will be after this change.
    _check_limits_fit(permissions, access)
    if payload.lead_access is not None:
        await _check_campaigns_exist(session, payload.lead_access)

    if "name" in update_data and update_data["name"] is not None:
        role.name = update_data["name"]
    if "description" in update_data:
        role.description = update_data["description"]
    if "is_active" in update_data and update_data["is_active"] is not None:
        role.is_active = update_data["is_active"]
    if payload.permissions is not None:
        role.permissions = permissions
    if payload.lead_access is not None:
        _apply_lead_access(role, payload.lead_access)

    role.updated_by_id = current_user.id
    await session.commit()
    await session.refresh(role)
    return await _role_read(session, role)


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
    if user_id == current_user.id:
        raise AuthorizationError("You can't change your own role.")
    target = await UserService(session).get_user(user_id)

    role_template = await _get_custom_role_or_404(payload.custom_role_id, session)
    if not role_template.is_active:
        raise ValidationError("This custom role is inactive and cannot be assigned.")
    await ensure_caller_holds(session, current_user, role_template.permissions or [])

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
    if user_id == current_user.id:
        raise AuthorizationError("You can't change your own role.")
    target = await UserService(session).get_user(user_id)

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
    await ensure_caller_holds(session, current_user, ROLE_PERMISSION_DEFAULTS.get(new_role, ()))

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
