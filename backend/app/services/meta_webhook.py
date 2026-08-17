"""Real-time Meta Lead Ads webhook ingestion (Phase 2).

Meta pushes each new leadgen lead to ONE public callback for ALL tenants, carrying only
a `page_id` + `leadgen_id`. This module:

1. Verifies the `X-Hub-Signature-256` HMAC over the RAW body with the app secret, so only
   genuine Meta deliveries are processed (`verify_signature`).
2. Routes each notification to its tenant via the PUBLIC `MetaPageRoute` (page_id → org +
   schema) — routing precedes any tenant-schema switch — then, under that tenant, decrypts
   the stored Page token, fetches the full lead (`get_lead`), maps it, and ingests it
   idempotently through the shared `LeadIngestService` (`process_payload`).

The poll (jobs/meta_lead_sync) remains the backstop: anything the webhook misses or drops
is re-ingested on the next poll (idempotent via the (source_provider, external_id) index),
so the endpoint can safely ACK 200 and let the poll heal transient failures. Platform
gating (per-org Facebook/Instagram toggles) mirrors the poll exactly.
"""
from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.config import get_settings
from app.core.crypto import decrypt_secret
from app.core.logging import get_logger
from app.core.tenancy import bypass, set_scope, set_tenant_schema
from app.database.enums import LeadIndustry, UserRole, UserStatus
from app.models.meta_connection import MetaConnection
from app.models.meta_page_route import MetaPageRoute
from app.models.organization import Organization
from app.models.user import User
from app.services.base import ServiceBase
from app.services.lead_ingest import LeadIngestService
from app.services.meta_graph import MetaGraphClient, MetaGraphError
from app.services.meta_mapper import map_meta_lead
from app.services.notifications import NotificationService

logger = get_logger(__name__)

_PROVIDER = "facebook"
_PLATFORMS: tuple[str, ...] = ("facebook", "instagram")
# Managers who get the "new leads arrived, assign them" nudge (shared with the poll).
_MANAGER_ROLES = (UserRole.sales_manager, UserRole.owner)


def verify_signature(raw_body: bytes, header: str | None) -> bool:
    """Constant-time-verify Meta's `X-Hub-Signature-256: sha256=<hex>` over the RAW request
    body using the app secret. False (reject) when the secret is unset — so the webhook is
    inert until configured — or the header is missing/malformed/mismatched."""
    secret = get_settings().meta_app_secret
    if not secret or not header or not header.startswith("sha256="):
        return False
    sent = header.split("=", 1)[1]
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    # Compare as BYTES: Starlette decodes header values as latin-1, so a crafted non-ASCII
    # byte in the signature would make the str form of compare_digest raise TypeError (a 500
    # on unauthenticated input). Byte comparison fails closed for any mismatch without raising.
    return hmac.compare_digest(sent.encode("utf-8"), expected.encode("ascii"))


async def notify_new_meta_leads(session, org_id, created: int) -> None:
    """Nudge an org's managers (RE + cross-vertical owner) that `created` new Meta leads
    landed in the triage pool and need assigning. Shared by the poll and the webhook."""
    manager_ids = (
        await session.execute(
            select(User.id).where(
                User.organization_id == org_id,
                User.role.in_(_MANAGER_ROLES),
                User.status == UserStatus.active,
                User.is_deleted.is_(False),
            )
        )
    ).scalars().all()
    if not manager_ids:
        return
    notif = NotificationService(session)
    plural = "s" if created != 1 else ""
    for manager_id in manager_ids:
        await notif.create_notification(
            user_id=manager_id,
            message=f"{created} new Meta lead{plural} arrived and need assigning.",
        )


class MetaWebhookService(ServiceBase):
    """Route + ingest a verified leadgen webhook payload. One instance per delivery."""

    def __init__(self, session):
        super().__init__(session)
        self.ingest = LeadIngestService(session)

    @staticmethod
    def _extract_targets(payload: object) -> list[tuple[str, str]]:
        """Pull unique (page_id, leadgen_id) pairs from a `page`/`leadgen` change payload.
        Tolerates junk/partial entries — a malformed change is skipped, never fatal."""
        if not isinstance(payload, dict) or payload.get("object") != "page":
            return []
        out: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for entry in payload.get("entry") or []:
            if not isinstance(entry, dict):
                continue
            for change in entry.get("changes") or []:
                if not isinstance(change, dict) or change.get("field") != "leadgen":
                    continue
                value = change.get("value")
                value = value if isinstance(value, dict) else {}
                page_id = str(value.get("page_id") or entry.get("id") or "")
                leadgen_id = str(value.get("leadgen_id") or "")
                if not page_id or not leadgen_id:
                    continue
                key = (page_id, leadgen_id)
                if key in seen:
                    continue
                seen.add(key)
                out.append(key)
        return out

    async def process_payload(self, payload: object) -> dict:
        """Route every leadgen notification to its tenant and ingest. Never raises for a
        single bad page — that page is rolled back and logged, the rest proceed."""
        counts = {"ingested": 0, "skipped": 0, "filtered": 0, "unrouted": 0, "errors": 0}
        targets = self._extract_targets(payload)
        if not targets:
            return counts

        by_page: dict[str, list[str]] = {}
        for page_id, leadgen_id in targets:
            by_page.setdefault(page_id, []).append(leadgen_id)

        for page_id, leadgen_ids in by_page.items():
            # Public routing table — resolve the tenant BEFORE touching any tenant schema.
            with bypass(self.session):
                route = (
                    await self.session.execute(
                        select(MetaPageRoute).where(MetaPageRoute.page_id == page_id)
                    )
                ).scalar_one_or_none()
            if route is None or not route.is_active:
                counts["unrouted"] += len(leadgen_ids)
                continue
            try:
                await self._ingest_page(route, leadgen_ids, counts)
            except Exception:  # noqa: BLE001 — one bad page must not sink the delivery
                await self.session.rollback()
                counts["errors"] += len(leadgen_ids)
                logger.warning("meta webhook ingest failed for page %s", page_id, exc_info=True)

        set_scope(self.session, None)
        return counts

    async def _ingest_page(self, route: MetaPageRoute, leadgen_ids: list[str], counts: dict) -> None:
        with bypass(self.session):
            org = (
                await self.session.execute(
                    select(Organization).where(Organization.id == route.organization_id)
                )
            ).scalar_one_or_none()
        if org is None or not org.is_active or org.is_deleted:
            counts["unrouted"] += len(leadgen_ids)
            return

        features = org.features or {}
        allowed = {p for p in _PLATFORMS if features.get(f"module.meta_{p}")}
        if not allowed:
            counts["filtered"] += len(leadgen_ids)  # neither platform granted for this org
            return

        set_scope(self.session, org.id)
        await set_tenant_schema(self.session, org.schema_name)
        conn = (
            await self.session.execute(
                select(MetaConnection).where(
                    MetaConnection.provider == _PROVIDER,
                    MetaConnection.page_id == route.page_id,
                    MetaConnection.is_active.is_(True),
                    MetaConnection.is_deleted.is_(False),
                )
            )
        ).scalar_one_or_none()
        if conn is None or conn.status == "needs_reauth":
            counts["unrouted"] += len(leadgen_ids)
            return

        try:
            token = decrypt_secret(conn.token_encrypted)
        except Exception:  # noqa: BLE001 — key rotated / corrupt cipher
            conn.status = "error"
            conn.status_detail = "Stored token could not be decrypted."
            await self.commit()
            counts["errors"] += len(leadgen_ids)
            return
        try:
            industry = LeadIndustry(conn.default_industry)
        except ValueError:
            conn.status = "error"
            conn.status_detail = f"Unknown industry '{conn.default_industry}'."
            await self.commit()
            counts["errors"] += len(leadgen_ids)
            return

        client = MetaGraphClient(token)
        created = 0
        for leadgen_id in leadgen_ids:
            # Idempotency shortcut: skip the Graph call entirely for a lead we already have
            # (Meta redelivers the same leadgen_id on retry — don't re-fetch or re-notify).
            if await self.ingest.find_by_external(conn.provider, leadgen_id) is not None:
                counts["skipped"] += 1
                continue
            try:
                raw = await client.get_lead(leadgen_id)
            except MetaGraphError as exc:
                counts["errors"] += 1
                if exc.is_auth_error:
                    # Token bad for the whole Page — stop and finalize below; the poll also
                    # surfaces re-auth. Any leads already created still notify.
                    conn.status = "needs_reauth"
                    conn.status_detail = str(exc)[:500]
                    break
                logger.warning("meta webhook get_lead failed for %s", leadgen_id, exc_info=True)
                continue
            external_id, _created_unix, fields = map_meta_lead(
                raw, conn.field_map, provider=conn.provider
            )
            if not external_id:
                counts["skipped"] += 1
                continue
            platform = "instagram" if fields.get("source") == "Instagram" else "facebook"
            if platform not in allowed:
                counts["filtered"] += 1  # platform disabled for this org
                continue
            _, was_created = await self.ingest.ingest_lead(
                organization_id=org.id,
                actor_id=conn.integration_user_id,
                industry=industry,
                source_provider=conn.provider,
                external_id=external_id,
                fields=fields,
            )
            if was_created:
                created += 1
                counts["ingested"] += 1
            else:
                counts["skipped"] += 1

        conn.last_synced_at = datetime.now(UTC)
        await self.commit()
        if created:
            await notify_new_meta_leads(self.session, org.id, created)
            await self.commit()
