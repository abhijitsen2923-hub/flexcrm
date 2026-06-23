from uuid import UUID

from sqlalchemy import select

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.permissions import LEGACY_ROLES, role_is_valid_for_industry
from app.core.security import hash_password
from app.core.tenancy import current_org
from app.database.enums import UserRole
from app.models.custom_role import CustomRole, UserCustomRoleAssignment
from app.models.organization import Organization
from app.repositories.refresh_tokens import RefreshTokenRepository
from app.repositories.users import UserRepository
from app.schemas.common import PaginationParams
from app.schemas.user import UserCreate, UserFilterParams, UserUpdate
from app.services.base import ServiceBase
from app.utils.query import validate_sort_field


class UserService(ServiceBase):
    allowed_sort_fields = {"created_at", "updated_at", "first_name", "last_name", "email", "status", "role"}

    def __init__(self, session):
        super().__init__(session)
        self.repository = UserRepository(session)
        self.refresh_token_repository = RefreshTokenRepository(session)

    async def list_users(self, pagination: PaginationParams, filters: UserFilterParams):
        sort_by = validate_sort_field(filters.sort_by, self.allowed_sort_fields)
        return await self.repository.list(
            pagination=pagination,
            filters={"role": filters.role, "status": filters.status},
            search=filters.search,
            search_fields=("first_name", "last_name", "email", "phone"),
            sort_by=sort_by,
            sort_order=filters.sort_order,
        )

    async def get_user(self, user_id: UUID):
        user = await self.repository.get(user_id)
        if user is None:
            raise NotFoundError("User not found.")
        return user

    async def create_user(self, payload: UserCreate, *, actor_id: UUID | None):
        if await self.repository.get_by_email(payload.email):
            raise ConflictError("A user with this email already exists.")

        if payload.role == UserRole.custom:
            if not payload.custom_role_id:
                raise ValidationError("custom_role_id is required when role is 'custom'.")
            # Validate the custom role exists and is active.
            template = (
                await self.session.execute(
                    select(CustomRole).where(CustomRole.id == payload.custom_role_id)
                )
            ).scalar_one_or_none()
            if not template:
                raise ValidationError("Custom role not found.")
            if not template.is_active:
                raise ValidationError("This custom role is inactive and cannot be assigned.")
        else:
            await self._validate_role_for_current_org(payload.role)

        user = await self.repository.create(
            {
                "first_name": payload.first_name,
                "last_name": payload.last_name,
                "email": payload.email,
                "password_hash": hash_password(payload.password),
                "role": payload.role,
                "phone": payload.phone,
                "status": payload.status,
                "created_by_id": actor_id,
                "updated_by_id": actor_id,
            }
        )
        await self.session.flush()  # get user.id before creating assignment

        if payload.role == UserRole.custom and payload.custom_role_id:
            self.session.add(UserCustomRoleAssignment(
                user_id=user.id,
                custom_role_id=payload.custom_role_id,
            ))

        await self.commit()
        return user

    async def update_user(self, user_id: UUID, payload: UserUpdate, *, actor_id: UUID | None):
        user = await self.get_user(user_id)
        update_data = payload.model_dump(exclude_unset=True)
        if "email" in update_data and update_data["email"] != user.email:
            if await self.repository.get_by_email(update_data["email"]):
                raise ConflictError("A user with this email already exists.")
        if "role" in update_data and update_data["role"] is not None:
            await self._validate_role_for_current_org(UserRole(update_data["role"]))
        if "password" in update_data:
            update_data["password_hash"] = hash_password(update_data.pop("password"))
        update_data["updated_by_id"] = actor_id
        user = await self.repository.update(user, update_data)
        await self.commit()
        return user

    async def _validate_role_for_current_org(self, role: UserRole) -> None:
        """Reject legacy roles and cross-vertical assignments (Phase 8).

        Legacy roles (admin/manager/sales) still exist in the enum so the 0010
        migration can read them during backfill — but assigning them via the
        API is not allowed post-migration. Vertical-locked roles must match the
        org's `business_type`.
        """
        if role in LEGACY_ROLES:
            raise ValidationError(
                f"Role '{role.value}' is a legacy role and no longer assignable. "
                f"Use one of the Phase 8 roles instead."
            )

        if role == UserRole.custom:
            raise ValidationError(
                "Use POST /users/{id}/custom-role to assign a custom role template."
            )

        org_id = current_org(self.session)
        if org_id is None:
            # No org scope on session — shouldn't happen for an authed call, but
            # if it does, allow only the universal roles.
            if not role_is_valid_for_industry(role, None):
                raise ValidationError(
                    f"Role '{role.value}' requires an organisation context."
                )
            return

        org = (
            await self.session.execute(select(Organization).where(Organization.id == org_id))
        ).scalar_one_or_none()
        industry = org.business_type if org else None
        if not role_is_valid_for_industry(role, industry):
            raise ValidationError(
                f"Role '{role.value}' is not valid for industry "
                f"'{industry.value if industry else 'unknown'}'."
            )

    async def delete_user(self, user_id: UUID, *, actor_id: UUID | None):
        user = await self.get_user(user_id)
        await self.repository.soft_delete(user, actor_id)
        await self.refresh_token_repository.revoke_for_user(user.id)
        await self.commit()
