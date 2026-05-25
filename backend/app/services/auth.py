from datetime import UTC, datetime
from uuid import UUID

from fastapi import BackgroundTasks
from sqlalchemy import select

from app.core.exceptions import AuthenticationError, ConflictError
from app.core.permissions import effective_permissions_for_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.core.tenancy import bypass, set_scope
from app.database.enums import UserRole, UserStatus
from app.models.organization import Organization
from app.models.user import User
from app.models.user_permission_grant import UserPermissionGrant
from app.repositories.refresh_tokens import RefreshTokenRepository
from app.repositories.users import UserRepository
from app.schemas.auth import LoginRequest, RefreshTokenRequest, RegisterRequest, TokenResponse
from app.schemas.user import UserRead
from app.services.base import ServiceBase
from app.services.email import EmailService


class AuthService(ServiceBase):
    def __init__(self, session):
        super().__init__(session)
        self.user_repository = UserRepository(session)
        self.refresh_token_repository = RefreshTokenRepository(session)
        self.email_service = EmailService()

    async def register(
        self,
        payload: RegisterRequest,
        *,
        background_tasks: BackgroundTasks | None = None,
        creator_id: UUID | None = None,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> TokenResponse:
        # Lookup of "is this email taken" must cross orgs — bypass the global
        # filter for it. The same is true for every read in this method until
        # we've created the new org and set scope on the session.
        with bypass(self.session):
            existing_user = await self.user_repository.get_by_email(payload.email)
            if existing_user:
                raise ConflictError("A user with this email already exists.")

            # Every public registration creates a fresh Organization. The user
            # becomes the admin of that org regardless of their requested role.
            org_name = (payload.organization_name or f"{payload.first_name}'s Workspace").strip()[:255]
            organization = Organization(
                name=org_name,
                business_type=payload.business_type,
                plan="free",
                features=None,
            )
            self.session.add(organization)
            await self.session.flush()

            user = User(
                first_name=payload.first_name,
                last_name=payload.last_name,
                email=payload.email,
                password_hash=hash_password(payload.password),
                # First user of an org is always `owner` (Phase 8 — was `admin`).
                role=UserRole.owner,
                phone=payload.phone,
                status=UserStatus.active,
                business_type=payload.business_type,
                organization_id=organization.id,
                created_by_id=creator_id,
                updated_by_id=creator_id,
            )
            self.session.add(user)
            await self.session.flush()

            # Mirror created_by/updated_by on the org for audit symmetry.
            organization.created_by_id = user.id
            organization.updated_by_id = user.id

            token_response = await self._issue_tokens(
                user.id,
                user.role.value,
                organization_id=organization.id,
                user_agent=user_agent,
                ip_address=ip_address,
            )

        # Scope the session before commit so any cache invalidation /
        # event-driven inserts that fire on commit are correctly stamped.
        set_scope(self.session, organization.id)
        await self.commit()

        if background_tasks:
            background_tasks.add_task(self.email_service.send_welcome_email, user.email, user.first_name)

        return await self._build_token_response_async(token_response, user)

    async def login(
        self,
        payload: LoginRequest,
        *,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> TokenResponse:
        # We don't know the org until after authentication — look up the user
        # with the global filter disabled.
        with bypass(self.session):
            user = await self.user_repository.get_by_email(payload.email)
            if user is None or not verify_password(payload.password, user.password_hash):
                raise AuthenticationError("Invalid email or password.")
            if user.status != UserStatus.active:
                raise AuthenticationError("This account is not active.")

            token_response = await self._issue_tokens(
                user.id,
                user.role.value,
                organization_id=user.organization_id,
                user_agent=user_agent,
                ip_address=ip_address,
            )

        set_scope(self.session, user.organization_id)
        await self.commit()
        return await self._build_token_response_async(token_response, user)

    async def refresh(
        self,
        payload: RefreshTokenRequest,
        *,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> TokenResponse:
        token_payload = decode_token(payload.refresh_token, refresh=True)
        if token_payload.get("type") != "refresh":
            raise AuthenticationError("Invalid refresh token.")

        with bypass(self.session):
            stored_token = await self.refresh_token_repository.get_active(token_payload["jti"])
            if stored_token is None:
                raise AuthenticationError("Refresh token is no longer valid.")

            user = await self.user_repository.get(UUID(token_payload["sub"]))
            if user is None or user.status != UserStatus.active:
                raise AuthenticationError("User account is not active.")

            await self.refresh_token_repository.revoke(stored_token)
            token_response = await self._issue_tokens(
                user.id,
                user.role.value,
                organization_id=user.organization_id,
                user_agent=user_agent,
                ip_address=ip_address,
            )

        set_scope(self.session, user.organization_id)
        await self.commit()
        return await self._build_token_response_async(token_response, user)

    async def logout(self, refresh_token: str) -> None:
        token_payload = decode_token(refresh_token, refresh=True)
        if token_payload.get("type") != "refresh":
            raise AuthenticationError("Invalid refresh token.")

        with bypass(self.session):
            stored_token = await self.refresh_token_repository.get_active(token_payload["jti"])
            if stored_token is None:
                return
            await self.refresh_token_repository.revoke(stored_token)
        await self.commit()

    async def _build_token_response_async(
        self,
        token_response: dict,
        user: User,
    ) -> TokenResponse:
        """Materialise a TokenResponse with the user's current effective permissions.

        Grants are loaded under `bypass(session)` because login/register run with
        the org scope freshly set (or about to be) — relying on the global filter
        is fine but bypassing avoids any ordering surprises on first login.
        """
        with bypass(self.session):
            grant_codes = (
                await self.session.execute(
                    select(UserPermissionGrant.permission_code).where(
                        UserPermissionGrant.user_id == user.id
                    )
                )
            ).scalars().all()
        effective = effective_permissions_for_user(user.role, grant_codes)

        user_read = UserRead.model_validate(user).model_copy(
            update={"permissions": sorted(code.value for code in effective)}
        )
        return TokenResponse(
            access_token=token_response["access_token"],
            refresh_token=token_response["refresh_token"],
            access_token_expires_at=token_response["access_token_expires_at"],
            refresh_token_expires_at=token_response["refresh_token_expires_at"],
            user=user_read,
        )

    async def _issue_tokens(
        self,
        user_id: UUID,
        role: str,
        *,
        organization_id: UUID | None = None,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> dict[str, str | datetime]:
        access_token, access_expires_at = create_access_token(
            str(user_id), role=role, organization_id=str(organization_id) if organization_id else None
        )
        refresh_token, refresh_expires_at = create_refresh_token(str(user_id))
        refresh_payload = decode_token(refresh_token, refresh=True)

        await self.refresh_token_repository.create(
            {
                "user_id": user_id,
                "token_id": refresh_payload["jti"],
                "expires_at": refresh_expires_at,
                "revoked_at": None,
                "user_agent": user_agent,
                "ip_address": ip_address,
            }
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "access_token_expires_at": access_expires_at,
            "refresh_token_expires_at": refresh_expires_at,
        }
