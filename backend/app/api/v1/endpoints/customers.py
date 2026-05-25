from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import pagination_params, require_permissions
from app.core.permissions import PermissionCode
from app.database.session import get_db_session
from app.schemas.common import MessageResponse, PaginatedResponse, PaginationParams, build_page_meta
from app.schemas.customer import CustomerCreate, CustomerFilterParams, CustomerRead, CustomerUpdate
from app.services.customers import CustomerService


router = APIRouter()


@router.get("", response_model=PaginatedResponse[CustomerRead])
async def list_customers(
    filters: CustomerFilterParams = Depends(),
    pagination: PaginationParams = Depends(pagination_params),
    _: object = Depends(require_permissions(PermissionCode.CUSTOMER_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    items, total = await CustomerService(session).list_customers(pagination, filters)
    return PaginatedResponse[CustomerRead](items=items, pagination=build_page_meta(total, pagination))


@router.get("/{customer_id}", response_model=CustomerRead)
async def get_customer(
    customer_id: UUID,
    _: object = Depends(require_permissions(PermissionCode.CUSTOMER_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    return await CustomerService(session).get_customer(customer_id)


@router.post("", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
async def create_customer(
    payload: CustomerCreate,
    current_user=Depends(require_permissions(PermissionCode.CUSTOMER_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    return await CustomerService(session).create_customer(payload, actor_id=current_user.id)


@router.put("/{customer_id}", response_model=CustomerRead)
async def update_customer(
    customer_id: UUID,
    payload: CustomerUpdate,
    current_user=Depends(require_permissions(PermissionCode.CUSTOMER_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    return await CustomerService(session).update_customer(customer_id, payload, actor_id=current_user.id)


@router.delete("/{customer_id}", response_model=MessageResponse)
async def delete_customer(
    customer_id: UUID,
    current_user=Depends(require_permissions(PermissionCode.CUSTOMER_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    await CustomerService(session).delete_customer(customer_id, actor_id=current_user.id)
    return MessageResponse(message="Customer deleted successfully.")
