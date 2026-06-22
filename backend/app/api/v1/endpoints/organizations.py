from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_permissions
from app.core.currencies import allowed_currencies_for_org
from app.core.exceptions import NotFoundError
from app.core.permissions import PermissionCode
from app.database.session import get_db_session
from app.models.organization import Organization
from app.schemas.organization import OrganizationRead, OrganizationUpdate, get_modules


router = APIRouter()


def _to_read(org: Organization) -> OrganizationRead:
    """Build the read schema with computed fields."""
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


@router.get("/me", response_model=OrganizationRead)
async def get_my_organization(
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """The Organization the current user belongs to."""
    org = (
        await session.execute(select(Organization).where(Organization.id == current_user.organization_id))
    ).scalar_one_or_none()
    if org is None:
        raise NotFoundError("Organization not found.")
    return _to_read(org)


@router.patch("/me", response_model=OrganizationRead)
async def update_my_organization(
    payload: OrganizationUpdate,
    current_user=Depends(require_permissions(PermissionCode.ORG_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    org = (
        await session.execute(select(Organization).where(Organization.id == current_user.organization_id))
    ).scalar_one_or_none()
    if org is None:
        raise NotFoundError("Organization not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(org, field, value)
    await session.commit()
    await session.refresh(org)
    return _to_read(org)
