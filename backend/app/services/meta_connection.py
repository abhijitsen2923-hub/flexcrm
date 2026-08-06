"""Tenant-facing Meta connection management: validate, connect, list, update, disconnect.

Bring-your-own-token: the admin pastes their own System-User token; we validate it
via a Graph probe, provision the per-org integration service user, encrypt the token,
and store the connection. The token is never returned. All operations are within the
caller's tenant schema (MetaConnection is a tenant table).
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.core.crypto import encrypt_secret
from app.core.exceptions import NotFoundError, ValidationError
from app.core.tenancy import current_org
from app.models.meta_connection import MetaConnection
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

    async def connect(self, req: MetaConnectRequest, *, actor_id: UUID) -> MetaConnection:
        """Validate + store a connection. Rejects if the token can't retrieve leads
        (so only working connections are saved). Re-connecting the same Page updates
        the existing row (re-paste token / re-map)."""
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

        conn = (
            await self.session.execute(
                select(MetaConnection).where(
                    MetaConnection.provider == _PROVIDER,
                    MetaConnection.page_id == req.page_id,
                    MetaConnection.is_deleted.is_(False),
                )
            )
        ).scalar_one_or_none()
        if conn is None:
            conn = MetaConnection(
                provider=_PROVIDER,
                page_id=req.page_id,
                default_industry=industry.value,
                token_encrypted=token_enc,
                field_map=req.field_map,
                integration_user_id=integration_user.id,
                created_by_id=actor_id,
                updated_by_id=actor_id,
            )
            self.session.add(conn)
        else:
            conn.token_encrypted = token_enc
            conn.integration_user_id = integration_user.id
            conn.is_active = True
            conn.updated_by_id = actor_id
            if req.field_map is not None:
                conn.field_map = req.field_map
        conn.page_name = result.page_name
        conn.status = "ok"
        conn.status_detail = None
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
        await self.commit()

    async def _org(self) -> Organization:
        org_id = current_org(self.session)
        org = (
            await self.session.execute(select(Organization).where(Organization.id == org_id))
        ).scalar_one_or_none()
        if org is None:
            raise NotFoundError("Organization not found.")
        return org
