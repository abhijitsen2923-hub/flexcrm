"""Platform-admin endpoints — only accessible to users with is_platform_admin=True.

These endpoints bypass org tenancy to read/write across all organizations.
Regular users always receive 403 from `require_platform_admin`.
"""
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, require_platform_admin
from app.core.cache import cache_client
from app.core.currencies import allowed_currencies_for_org
from app.core.exceptions import NotFoundError, ValidationError
from app.core.tenancy import bypass
from app.models.organization import Organization
from app.models.user import User
from app.schemas.organization import (
    MODULE_KEYS,
    OrganizationRead,
    SetOrgStatusRequest,
    UpdateModulesRequest,
    get_modules,
)
from app.services.tenant_provisioner import _SAFE_SCHEMA
from app.services.tenant_repair import repair_tenant_enums


router = APIRouter()


@router.post("/tenant-enums/repair")
async def repair_tenant_enums_endpoint(
    dry_run: bool = Query(True, description="Preview only; set false to apply."),
    _=Depends(require_platform_admin()),
):
    """Idempotently repair tenant schemas whose enum columns were created as
    tenant-local shadows of the public enum types (older tenants). dry_run=true
    (default) reports what would change without writing. Safe to re-run."""
    results = await repair_tenant_enums(dry_run=dry_run)
    return {"dry_run": dry_run, "results": results}


def _to_read(org: Organization) -> OrganizationRead:
    return OrganizationRead(
        id=org.id,
        name=org.name,
        business_type=org.business_type,
        plan=org.plan,
        features=org.features,
        allowed_currencies=allowed_currencies_for_org(org),
        modules=get_modules(org.features),
        is_active=org.is_active,
        is_deleted=org.is_deleted,
        created_at=org.created_at,
        updated_at=org.updated_at,
    )


async def _load_org(session: AsyncSession, org_id: UUID, *, include_deleted: bool = False) -> Organization:
    conditions = [Organization.id == org_id]
    if not include_deleted:
        conditions.append(Organization.is_deleted.is_(False))
    org = (
        await session.execute(select(Organization).where(*conditions))
    ).scalar_one_or_none()
    if org is None:
        raise NotFoundError("Organization not found.")
    return org


async def _reject_if_platform_org(session: AsyncSession, org_id: UUID) -> None:
    """Block lifecycle changes to an org that hosts a platform admin (the
    FlexCRM Platform org), so operators can't lock themselves out."""
    has_platform_admin = (
        await session.execute(
            select(User.id).where(
                User.organization_id == org_id,
                User.is_platform_admin.is_(True),
            ).limit(1)
        )
    ).scalar_one_or_none()
    if has_platform_admin is not None:
        raise ValidationError("This is a platform organization and cannot be disabled or deleted.")


@router.get("/organizations", response_model=list[OrganizationRead])
async def list_organizations(
    include_archived: bool = Query(False),
    _=Depends(require_platform_admin()),
    session: AsyncSession = Depends(get_db_session),
):
    """List CLIENT organizations across all tenants (platform admin only).

    Platform organizations — those hosting a platform admin, i.e. the operator's
    own FlexCRM Platform org — are excluded; the SaaS operator manages client
    tenants, not their own org. Archived (is_deleted) orgs are excluded unless
    include_archived is true.
    """
    with bypass(session):
        platform_org_ids = (
            select(User.organization_id).where(
                User.is_platform_admin.is_(True),
                User.organization_id.is_not(None),
            )
        )
        conditions = [Organization.id.not_in(platform_org_ids)]
        if not include_archived:
            conditions.append(Organization.is_deleted.is_(False))
        orgs = (
            await session.execute(
                select(Organization).where(*conditions).order_by(Organization.name)
            )
        ).scalars().all()
    return [_to_read(org) for org in orgs]


@router.patch("/organizations/{org_id}/modules", response_model=OrganizationRead)
async def update_org_modules(
    org_id: UUID,
    payload: UpdateModulesRequest,
    _=Depends(require_platform_admin()),
    session: AsyncSession = Depends(get_db_session),
):
    """Enable or disable optional modules for a specific organization."""
    with bypass(session):
        org = await _load_org(session, org_id)

        # Merge module flags into the existing features dict, preserving any
        # non-module keys (e.g. currency.options).
        features = dict(org.features or {})
        for key, enabled in payload.modules.items():
            if key in MODULE_KEYS:
                features[f"module.{key}"] = enabled
        org.features = features

        await session.commit()
        await session.refresh(org)
    return _to_read(org)


@router.patch("/organizations/{org_id}/status", response_model=OrganizationRead)
async def set_org_status(
    org_id: UUID,
    payload: SetOrgStatusRequest,
    _=Depends(require_platform_admin()),
    session: AsyncSession = Depends(get_db_session),
):
    """Disable (suspend) or enable a client organization."""
    with bypass(session):
        org = await _load_org(session, org_id)
        if not payload.is_active:
            await _reject_if_platform_org(session, org_id)
        org.is_active = payload.is_active
        await session.commit()
        await session.refresh(org)
    # Drop the cached org context so the new status takes effect immediately.
    await cache_client.delete(f"schema:{org_id}")
    return _to_read(org)


@router.delete("/organizations/{org_id}", response_model=OrganizationRead)
async def archive_organization(
    org_id: UUID,
    admin=Depends(require_platform_admin()),
    session: AsyncSession = Depends(get_db_session),
):
    """Archive (soft-delete) a client organization.

    The org record and its tenant data are retained and can be restored; access
    is blocked immediately. Not permitted for the platform organization.
    """
    with bypass(session):
        org = await _load_org(session, org_id)
        await _reject_if_platform_org(session, org_id)
        org.is_deleted = True
        org.deleted_at = datetime.now(UTC)
        org.deleted_by_id = admin.id
        await session.commit()
        await session.refresh(org)
    await cache_client.delete(f"schema:{org_id}")
    return _to_read(org)


@router.post("/organizations/{org_id}/restore", response_model=OrganizationRead)
async def restore_organization(
    org_id: UUID,
    _=Depends(require_platform_admin()),
    session: AsyncSession = Depends(get_db_session),
):
    """Restore a previously archived organization."""
    with bypass(session):
        org = await _load_org(session, org_id, include_deleted=True)
        org.is_deleted = False
        org.deleted_at = None
        org.deleted_by_id = None
        await session.commit()
        await session.refresh(org)
    await cache_client.delete(f"schema:{org_id}")
    return _to_read(org)


@router.delete("/organizations/{org_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
async def purge_organization(
    org_id: UUID,
    _=Depends(require_platform_admin()),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Permanently delete an archived organization and ALL its data.

    Drops the tenant schema (every per-tenant table/row) and removes the org
    row, which cascades to its users and refresh tokens. Irreversible. Only
    allowed once the org has been archived (is_deleted) and never for the
    platform organization.
    """
    with bypass(session):
        org = await _load_org(session, org_id, include_deleted=True)
        await _reject_if_platform_org(session, org_id)
        if not org.is_deleted:
            raise ValidationError("Archive the organization before deleting it permanently.")
        schema = org.schema_name
        if not _SAFE_SCHEMA.match(schema):
            raise ValidationError("Refusing to drop a tenant schema with an unsafe name.")

        # Drop the tenant schema (all its tables/data) and delete the org row on
        # THIS session's connection, in one transaction. A separate connection
        # for the DROP would deadlock: dropping the tenant tables' cross-schema
        # FKs needs a lock on public.users, but this session already holds
        # ACCESS SHARE locks on users/organizations from the reads above and
        # won't release them until commit — so the DROP hangs the request.
        # PostgreSQL DDL is transactional, so doing both here is safe. Dropping
        # the schema first clears the tenant->public.users FKs; the raw DELETE
        # then relies on ON DELETE CASCADE to remove the org's users and their
        # refresh tokens (the ORM would null the FKs instead).
        await session.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await session.execute(
            text("DELETE FROM organizations WHERE id = :id"), {"id": org_id}
        )
        await session.commit()

    await cache_client.delete(f"schema:{org_id}")
