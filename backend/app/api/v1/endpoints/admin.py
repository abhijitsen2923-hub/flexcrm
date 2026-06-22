"""Platform-admin endpoints — only accessible to users with is_platform_admin=True.

These endpoints bypass org tenancy to read/write across all organizations.
Regular users always receive 403 from `require_platform_admin`.
"""
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, require_platform_admin
from app.core.currencies import allowed_currencies_for_org
from app.core.exceptions import NotFoundError
from app.core.tenancy import bypass
from app.models.organization import Organization
from app.schemas.organization import MODULE_KEYS, OrganizationRead, UpdateModulesRequest, get_modules


router = APIRouter()


def _to_read(org: Organization) -> OrganizationRead:
    return OrganizationRead(
        id=org.id,
        name=org.name,
        business_type=org.business_type,
        plan=org.plan,
        features=org.features,
        allowed_currencies=allowed_currencies_for_org(org),
        modules=get_modules(org.features),
        created_at=org.created_at,
        updated_at=org.updated_at,
    )


@router.get("/organizations", response_model=list[OrganizationRead])
async def list_organizations(
    _=Depends(require_platform_admin()),
    session: AsyncSession = Depends(get_db_session),
):
    """List all organizations across all tenants (platform admin only)."""
    with bypass(session):
        orgs = (
            await session.execute(
                select(Organization)
                .where(Organization.is_deleted.is_(False))
                .order_by(Organization.name)
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
        org = (
            await session.execute(
                select(Organization).where(
                    Organization.id == org_id,
                    Organization.is_deleted.is_(False),
                )
            )
        ).scalar_one_or_none()
        if org is None:
            raise NotFoundError("Organization not found.")

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
