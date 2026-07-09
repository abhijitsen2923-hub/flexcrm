import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import pagination_params, require_permissions
from app.core.permissions import PermissionCode
from app.database.enums import UserRole
from app.database.session import get_db_session
from app.schemas.common import MessageResponse, PaginatedResponse, PaginationParams, build_page_meta
from app.schemas.customer import CustomerCreate, CustomerFilterParams, CustomerRead, CustomerUpdate
from app.schemas.user import UserCreate
from app.services.customers import CustomerService
from app.services.users import UserService


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


@router.post("/{customer_id}/portal-access")
async def grant_portal_access(
    customer_id: UUID,
    current_user=Depends(require_permissions(PermissionCode.CUSTOMER_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    """Provision a buyer self-service portal login for a customer.

    Creates a `customer`-role user matched to the customer's email and returns a
    temporary password for staff to share. Reuses UserService so email-uniqueness,
    org scoping and password hashing all follow the standard path. 409 if a login
    already exists for that email; 400 if the customer has no email.
    """
    customer = await CustomerService(session).get_customer(customer_id)
    if not customer.email:
        raise HTTPException(
            status_code=400,
            detail="Add an email to this customer before creating a portal login.",
        )
    temporary_password = secrets.token_urlsafe(9)
    first, _, last = (customer.contact_name or "Customer").partition(" ")
    await UserService(session).create_user(
        UserCreate(
            first_name=first or "Customer",
            last_name=last or "-",
            email=customer.email,
            password=temporary_password,
            role=UserRole.customer,
        ),
        actor_id=current_user.id,
    )
    return {"email": customer.email, "temporary_password": temporary_password}
