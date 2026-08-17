"""Tenant-facing Meta connection management: validate, connect, list, update, disconnect.

Bring-your-own-token: the admin pastes their own System-User token; we validate it
via a Graph probe, provision the per-org integration service user, encrypt the token,
and store the connection. The token is never returned. All operations are within the
caller's tenant schema (MetaConnection is a tenant table).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select

from app.core.crypto import encrypt_secret
from app.core.exceptions import NotFoundError, ValidationError
from app.core.tenancy import current_org
from app.models.meta_connection import MetaConnection
from app.models.meta_page_route import MetaPageRoute
from app.models.organization import Organization
from app.schemas.meta import MetaConnectionUpdate, MetaConnectRequest, MetaValidateResult
from app.services.base import ServiceBase
from app.services.meta_graph import MetaGraphClient, MetaGraphError
from app.services.users import UserService

_PROVIDER = "facebook"


class MetaConnectionService(ServiceBase):
    async def validate(self, page_id: str, token: str) -> MetaValidateResult:
        """Probe the token: resolve the Page (proves token+page), then list leadgen
        forms (proves the Lead-Access grant). Classifies the failure so the wizard
        can guide the admin precisely."""
        client = MetaGraphClient(token)
        try:
            page = await client.probe_page(page_id)
        except MetaGraphError as exc:
            return MetaValidateResult(ok=False, reason=self._classify(exc), detail=str(exc))
        try:
            forms = await client.list_leadgen_forms(page_id)
        except MetaGraphError as exc:
            # Token + Page resolve, but the leads edge is denied → missing Lead Access.
            return MetaValidateResult(
                ok=False,
                page_name=page.get("name"),
                reason="invalid_token" if exc.is_auth_error else "missing_lead_access",
                detail=str(exc),
            )
        return MetaValidateResult(ok=True, page_name=page.get("name"), form_count=len(forms))

    @staticmethod
    def _classify(exc: MetaGraphError) -> str:
        if exc.is_auth_error:
            return "invalid_token"
        return "error"

    async def list_connections(self) -> list[MetaConnection]:
        rows = (
            await self.session.execute(
                select(MetaConnection)
                .where(MetaConnection.is_deleted.is_(False))
                .order_by(MetaConnection.created_at.desc())
            )
        ).scalars().all()
        return list(rows)

    async def _get(self, connection_id: UUID) -> MetaConnection:
        conn = (
            await self.session.execute(
                select(MetaConnection).where(
                    MetaConnection.id == connection_id, MetaConnection.is_deleted.is_(False)
                )
            )
        ).scalar_one_or_none()
        if conn is None:
            raise NotFoundError("Meta connection not found.")
        return conn

    # --- shared connect/disconnect helpers ---------------------------------

    async def _find_connection(self, page_id: str) -> MetaConnection | None:
        """The connection for this page INCLUDING soft-deleted rows. Reconnecting must
        REVIVE the soft-deleted row, not INSERT a new one — the (provider, page_id)
        unique constraint is not soft-delete-aware, so a fresh insert would collide
        with the still-present soft-deleted row (a 409 that locks the Page out)."""
        return (
            await self.session.execute(
                select(MetaConnection).where(
                    MetaConnection.provider == _PROVIDER,
                    MetaConnection.page_id == page_id,
                )
            )
        ).scalar_one_or_none()

    async def _register_page_route(self, page_id: str, org: Organization) -> None:
        """Enforce "one Page ↔ one tenant" PLATFORM-WIDE and (re)register the public
        page→tenant router. Called by BOTH connect paths (BYO + OAuth) so the invariant
        holds regardless of method. Raises if the Page is already owned by another org."""
        route = (
            await self.session.execute(
                select(MetaPageRoute).where(MetaPageRoute.page_id == page_id)
            )
        ).scalar_one_or_none()
        if route is not None and route.organization_id != org.id:
            raise ValidationError(
                "This Facebook Page is already connected to another FlexCRM workspace."
            )
        if route is None:
            self.session.add(
                MetaPageRoute(
                    page_id=page_id,
                    organization_id=org.id,
                    schema_name=org.schema_name,
                    is_active=True,
                )
            )
        else:
            route.is_active = True
            route.schema_name = org.schema_name

    async def _release_page_route(self, page_id: str, org_id: UUID | None) -> None:
        """Free the public router on disconnect so the Page can be reconnected — by this
        org, or legitimately by another workspace. Only removes a route this org owns."""
        route = (
            await self.session.execute(
                select(MetaPageRoute).where(MetaPageRoute.page_id == page_id)
            )
        ).scalar_one_or_none()
        if route is not None and route.organization_id == org_id:
            await self.session.delete(route)

    @staticmethod
    def _revive(conn: MetaConnection) -> None:
        """Clear soft-delete so a reconnect reuses the existing (provider, page_id) row."""
        conn.is_deleted = False
        conn.deleted_at = None
        conn.is_active = True

    async def connect(self, req: MetaConnectRequest, *, actor_id: UUID) -> MetaConnection:
        """Validate + store a bring-your-own-token connection. Rejects if the token can't
        retrieve leads (so only working connections are saved). Re-connecting the same
        Page revives/updates the existing row (re-paste token / re-map)."""
        result = await self.validate(req.page_id, req.token)
        if not result.ok:
            raise ValidationError(
                f"Could not connect ({result.reason}): {result.detail or 'validation failed'}"
            )

        org = await self._org()
        industry = org.business_type
        if industry is None:
            raise ValidationError("This organization has no business type set; cannot connect.")

        integration_user = await UserService(self.session).get_or_create_integration_user(
            organization_id=org.id, business_type=industry
        )
        token_enc = encrypt_secret(req.token)

        conn = await self._find_connection(req.page_id)
        if conn is None:
            conn = MetaConnection(
                provider=_PROVIDER,
                page_id=req.page_id,
                auth_type="byo",
                default_industry=industry.value,
                token_encrypted=token_enc,
                field_map=req.field_map,
                integration_user_id=integration_user.id,
                created_by_id=actor_id,
                updated_by_id=actor_id,
            )
            self.session.add(conn)
        else:
            self._revive(conn)
            conn.auth_type = "byo"
            conn.token_encrypted = token_enc
            conn.integration_user_id = integration_user.id
            conn.updated_by_id = actor_id
            if req.field_map is not None:
                conn.field_map = req.field_map
        conn.page_name = result.page_name
        conn.status = "ok"
        conn.status_detail = None
        # Register the public route LAST — the friendly cross-org check still runs here,
        # but the route INSERT then flushes only at commit(), so a genuine same-page race
        # maps IntegrityError → ConflictError(409) rather than a raw pre-commit 500.
        await self._register_page_route(req.page_id, org)
        await self.commit()
        return conn

    async def create_oauth_connection(
        self,
        *,
        page_id: str,
        page_name: str | None,
        page_token: str,
        user_token: str,
        granted_scopes: list[str] | None,
        user_token_expires_in: int | None,
        actor_id: UUID,
    ) -> MetaConnection:
        """Store a connection obtained via the "Connect Facebook" OAuth flow. Runs in
        the caller's (authenticated) tenant schema. Encrypts both the Page token (used
        to read leads) and the long-lived user token (used to refresh). Also writes the
        PUBLIC page→tenant router, enforcing "one Page ↔ one tenant" across all orgs."""
        org = await self._org()
        industry = org.business_type
        if industry is None:
            raise ValidationError("This organization has no business type set; cannot connect.")

        integration_user = await UserService(self.session).get_or_create_integration_user(
            organization_id=org.id, business_type=industry
        )
        expires_at = None
        if user_token_expires_in:
            expires_at = datetime.now(UTC) + timedelta(seconds=int(user_token_expires_in))

        conn = await self._find_connection(page_id)
        if conn is None:
            conn = MetaConnection(
                provider=_PROVIDER,
                page_id=page_id,
                page_name=page_name,
                auth_type="oauth",
                default_industry=industry.value,
                token_encrypted=encrypt_secret(page_token),
                user_token_encrypted=encrypt_secret(user_token),
                token_expires_at=expires_at,
                granted_scopes=granted_scopes,
                integration_user_id=integration_user.id,
                created_by_id=actor_id,
                updated_by_id=actor_id,
            )
            self.session.add(conn)
        else:
            self._revive(conn)
            conn.auth_type = "oauth"
            conn.page_name = page_name
            conn.token_encrypted = encrypt_secret(page_token)
            conn.user_token_encrypted = encrypt_secret(user_token)
            conn.token_expires_at = expires_at
            conn.granted_scopes = granted_scopes
            conn.integration_user_id = integration_user.id
            conn.updated_by_id = actor_id
        conn.status = "ok"
        conn.status_detail = None
        # Register the public route LAST (see connect()) so a cross-org race becomes a
        # clean 409 at commit rather than a raw IntegrityError at an earlier flush.
        await self._register_page_route(page_id, org)
        await self.commit()
        return conn

    async def update(self, connection_id: UUID, payload: MetaConnectionUpdate, *, actor_id: UUID) -> MetaConnection:
        conn = await self._get(connection_id)
        if payload.token is not None:
            # Re-paste: re-validate before replacing so we don't silently store a bad token.
            result = await self.validate(conn.page_id, payload.token)
            if not result.ok:
                raise ValidationError(
                    f"Token rejected ({result.reason}): {result.detail or 'validation failed'}"
                )
            conn.token_encrypted = encrypt_secret(payload.token)
            conn.page_name = result.page_name
            conn.status = "ok"
            conn.status_detail = None
        if payload.field_map is not None:
            conn.field_map = payload.field_map
        if payload.is_active is not None:
            conn.is_active = payload.is_active
        conn.updated_by_id = actor_id
        await self.commit()
        return conn

    async def disconnect(self, connection_id: UUID, *, actor_id: UUID) -> None:
        conn = await self._get(connection_id)
        conn.is_deleted = True
        conn.is_active = False
        conn.updated_by_id = actor_id
        # Free the public page→tenant router so the Page can be reconnected later (by
        # this org, or another workspace once it's genuinely theirs). Without this the
        # Page stays claimed forever and nobody can reconnect it.
        await self._release_page_route(conn.page_id, current_org(self.session))
        await self.commit()

    async def _org(self) -> Organization:
        org_id = current_org(self.session)
        org = (
            await self.session.execute(select(Organization).where(Organization.id == org_id))
        ).scalar_one_or_none()
        if org is None:
            raise NotFoundError("Organization not found.")
        return org
