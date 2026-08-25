"""Inbound lead-source (99acres) connection + delivery service.

Covers the tenant-facing side (mint/list/disconnect a connection) and the public webhook side
(resolve the URL token → tenant, persist the raw delivery, then process it into a CRM lead).

Auth = secret-in-URL: `create_connection` mints a random token, stores only its SHA-256 hash in
the public `lead_source_routes` (+ the tenant `lead_source_connections`), and returns the plaintext
token ONCE. Inbound requests carry the token in the path; `resolve_route` hashes it and looks it up.

Safety = persist-then-process: the endpoint persists the raw body (its own commit) and ACKs 200
before `process_delivery` maps + ingests, so a processing fault never loses a paid-for lead — the
delivery row is replayable by the reconcile cron (P4). Ingest is idempotent on `external_id`.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.core.exceptions import NotFoundError, ValidationError
from app.core.tenancy import bypass, current_org
from app.database.enums import LeadIndustry
from app.models.lead_source_connection import LeadSourceConnection
from app.models.lead_source_delivery import LeadSourceDelivery
from app.models.lead_source_route import LeadSourceRoute
from app.models.organization import Organization
from app.services.base import ServiceBase
from app.services.lead_ingest import LeadIngestService
from app.services.lead_source_mapper import map_99acres_lead
from app.services.users import UserService

_PROVIDER = "99acres"


class LeadSourceService(ServiceBase):
    def __init__(self, session):
        super().__init__(session)
        self.ingest = LeadIngestService(session)

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    async def _org(self) -> Organization:
        org_id = current_org(self.session)
        org = (
            await self.session.execute(select(Organization).where(Organization.id == org_id))
        ).scalar_one_or_none()
        if org is None:
            raise NotFoundError("Organization not found.")
        return org

    # --- tenant-facing ------------------------------------------------------

    async def create_connection(self, *, label: str | None, actor_id: UUID) -> tuple[LeadSourceConnection, str]:
        """Mint a connection: generate a secret URL token, store its hash on the tenant
        connection + the public route, and return (connection, plaintext_token). The token is
        shown to the admin ONCE — only its hash is persisted."""
        org = await self._org()
        industry = org.business_type
        if industry is None:
            raise ValidationError("This organization has no business type set; cannot connect.")
        integration_user = await UserService(self.session).get_or_create_integration_user(
            organization_id=org.id, business_type=industry
        )
        token = "c_" + secrets.token_urlsafe(24)
        token_hash = self._hash_token(token)

        conn = LeadSourceConnection(
            provider=_PROVIDER,
            token_hash=token_hash,
            label=label,
            default_industry=industry.value,
            integration_user_id=integration_user.id,
            status="ok",
            is_active=True,
            created_by_id=actor_id,
            updated_by_id=actor_id,
        )
        self.session.add(conn)
        # Register the PUBLIC route last so a same-token race flushes at commit → ConflictError
        # (409) rather than a raw pre-commit error (mirrors MetaConnectionService._register_page_route).
        self.session.add(
            LeadSourceRoute(
                provider=_PROVIDER,
                token_hash=token_hash,
                organization_id=org.id,
                schema_name=org.schema_name,
                is_active=True,
            )
        )
        await self.commit()
        return conn, token

    async def list_connections(self) -> list[LeadSourceConnection]:
        rows = (
            await self.session.execute(
                select(LeadSourceConnection)
                .where(
                    LeadSourceConnection.provider == _PROVIDER,
                    LeadSourceConnection.is_deleted.is_(False),
                )
                .order_by(LeadSourceConnection.created_at.desc())
            )
        ).scalars().all()
        return list(rows)

    async def disconnect(self, connection_id: UUID, *, actor_id: UUID) -> None:
        conn = (
            await self.session.execute(
                select(LeadSourceConnection).where(
                    LeadSourceConnection.id == connection_id,
                    LeadSourceConnection.is_deleted.is_(False),
                )
            )
        ).scalar_one_or_none()
        if conn is None:
            raise NotFoundError("Connection not found.")
        conn.is_deleted = True
        conn.is_active = False
        conn.updated_by_id = actor_id
        # Release the public route so the token stops resolving (and the account can reconnect).
        with bypass(self.session):
            route = (
                await self.session.execute(
                    select(LeadSourceRoute).where(LeadSourceRoute.token_hash == conn.token_hash)
                )
            ).scalar_one_or_none()
            if route is not None:
                await self.session.delete(route)
        await self.commit()

    # --- webhook side -------------------------------------------------------

    async def resolve_route(self, token: str) -> LeadSourceRoute | None:
        """Hash the URL token and resolve the active public route (org + schema). Public table —
        safe to read before any tenant schema is active."""
        token_hash = self._hash_token(token)
        with bypass(self.session):
            return (
                await self.session.execute(
                    select(LeadSourceRoute).where(
                        LeadSourceRoute.provider == _PROVIDER,
                        LeadSourceRoute.token_hash == token_hash,
                        LeadSourceRoute.is_active.is_(True),
                    )
                )
            ).scalar_one_or_none()

    async def persist_delivery(self, token_hash: str, payload: dict) -> UUID:
        """Durably store the raw body BEFORE processing (own commit). Runs after the caller has
        set the tenant schema. Takes the resolved token_hash (not the route object, which may be
        detached from an earlier session). Returns the delivery id to process after the ACK."""
        conn = (
            await self.session.execute(
                select(LeadSourceConnection).where(
                    LeadSourceConnection.provider == _PROVIDER,
                    LeadSourceConnection.token_hash == token_hash,
                    LeadSourceConnection.is_deleted.is_(False),
                )
            )
        ).scalar_one_or_none()
        delivery = LeadSourceDelivery(
            provider=_PROVIDER,
            connection_id=(conn.id if conn else None),
            payload=payload,
            status="received",
        )
        self.session.add(delivery)
        await self.commit()
        return delivery.id

    async def mark_delivery(self, delivery_id: UUID, *, status: str, error: str | None = None) -> None:
        """Set a delivery's terminal status (e.g. 'ignored' for a body missing required fields).
        Keeps the row for audit/replay rather than discarding it."""
        delivery = (
            await self.session.execute(
                select(LeadSourceDelivery).where(LeadSourceDelivery.id == delivery_id)
            )
        ).scalar_one_or_none()
        if delivery is not None:
            delivery.status = status
            delivery.error = error
            delivery.processed_at = datetime.now(UTC)
            await self.commit()

    async def process_delivery(self, delivery_id: UUID, *, organization_id: UUID) -> str:
        """Map + ingest one stored delivery. Idempotent: safe to re-run (ingest dedupes on
        external_id; an already-processed row is a no-op). Marks the delivery processed/failed.
        Runs with the tenant schema already set by the caller. Never raises."""
        delivery = (
            await self.session.execute(
                select(LeadSourceDelivery).where(LeadSourceDelivery.id == delivery_id)
            )
        ).scalar_one_or_none()
        if delivery is None:
            return "missing"
        if delivery.status == "processed":
            return "already"

        try:
            external_id, fields = map_99acres_lead(delivery.payload)
            if not external_id or not (fields.get("contact_phone") or fields.get("contact_email")):
                delivery.status = "ignored"
                delivery.error = "No usable contact (phone/email) or external id."
                delivery.processed_at = datetime.now(UTC)
                await self.commit()
                return "ignored"

            conn = None
            if delivery.connection_id is not None:
                conn = (
                    await self.session.execute(
                        select(LeadSourceConnection).where(
                            LeadSourceConnection.id == delivery.connection_id
                        )
                    )
                ).scalar_one_or_none()
            industry = await self._industry_for(conn, organization_id)
            actor_id = conn.integration_user_id if conn else None
            if actor_id is None:
                # Connection lost its service user (SET NULL) — reprovision so leads have an owner.
                actor_id = (
                    await UserService(self.session).get_or_create_integration_user(
                        organization_id=organization_id, business_type=industry
                    )
                ).id

            lead, created = await self.ingest.ingest_lead(
                organization_id=organization_id,
                actor_id=actor_id,
                industry=industry,
                source_provider=_PROVIDER,
                external_id=external_id,
                fields=fields,
            )
            delivery.external_id = external_id
            delivery.lead_id = lead.id if lead else None
            delivery.status = "processed"
            delivery.processed_at = datetime.now(UTC)
            if conn is not None:
                if created:
                    conn.last_lead_at = datetime.now(UTC)
                account = str(delivery.payload.get("Username") or delivery.payload.get("username") or "").strip()
                if account and not conn.external_account_id:
                    conn.external_account_id = account[:64]
            await self.commit()
            return "created" if created else "duplicate"
        except Exception as exc:  # noqa: BLE001 — never raise; the reconcile cron retries
            await self.session.rollback()
            stale = (
                await self.session.execute(
                    select(LeadSourceDelivery).where(LeadSourceDelivery.id == delivery_id)
                )
            ).scalar_one_or_none()
            if stale is not None and stale.status != "processed":
                stale.status = "failed"
                stale.error = str(exc)[:1000]
                await self.commit()
            return "failed"

    async def _industry_for(self, conn: LeadSourceConnection | None, organization_id: UUID) -> LeadIndustry:
        if conn is not None and conn.default_industry:
            try:
                return LeadIndustry(conn.default_industry)
            except ValueError:
                pass
        # Fallback (connection missing/misconfigured): the org's actual business type, so a
        # replayed delivery for a non-real-estate org still lands in the right vertical/pipeline.
        with bypass(self.session):
            org = (
                await self.session.execute(
                    select(Organization).where(Organization.id == organization_id)
                )
            ).scalar_one_or_none()
        if org is not None and org.business_type is not None:
            return org.business_type
        return LeadIndustry.real_estate
