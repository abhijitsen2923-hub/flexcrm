from datetime import datetime
from uuid import UUID

from pydantic import EmailStr, Field

from app.database.enums import LeadIndustry, UserRole, UserStatus
from app.schemas.common import ORMModel, SearchSortParams


class UserSummary(ORMModel):
    id: UUID
    first_name: str
    last_name: str
    email: EmailStr
    role: UserRole
    status: UserStatus
    business_type: LeadIndustry | None = None
    organization_id: UUID | None = None
    is_platform_admin: bool = False
    # Effective permissions for this user (role defaults ∪ explicit grants,
    # alias-expanded). Empty on list endpoints — populated only on `/me`,
    # login, and refresh where the caller is identifying themselves.
    permissions: list[str] = Field(default_factory=list)


class UserCreate(ORMModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: UserRole
    phone: str | None = Field(default=None, max_length=32)
    status: UserStatus = UserStatus.active
    business_type: LeadIndustry | None = None


class UserUpdate(ORMModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    role: UserRole | None = None
    phone: str | None = Field(default=None, max_length=32)
    status: UserStatus | None = None
    business_type: LeadIndustry | None = None


class UserRead(UserSummary):
    phone: str | None = None
    created_at: datetime
    updated_at: datetime


class UserFilterParams(SearchSortParams):
    role: UserRole | None = None
    status: UserStatus | None = None
