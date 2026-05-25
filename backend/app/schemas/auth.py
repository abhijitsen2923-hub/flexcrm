from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.database.enums import LeadIndustry, UserRole
from app.schemas.user import UserRead


class RegisterRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    phone: str | None = Field(default=None, max_length=32)
    # `role` is accepted for backward compat but ignored — every first user of
    # a new org is `owner` (Phase 8). Kept on the schema so older clients keep
    # working without a 422.
    role: UserRole = UserRole.owner
    # Industry of the registering business. Stored on the new Organization;
    # every user inside the org inherits it.
    business_type: LeadIndustry
    # Organization name. Each registration creates a new Organization with the
    # registering user as its first admin. (Joining an existing org via invite
    # is a future feature.) If omitted, defaults to "{first_name}'s Workspace".
    organization_name: str | None = Field(default=None, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    access_token_expires_at: datetime
    refresh_token_expires_at: datetime
    user: UserRead
