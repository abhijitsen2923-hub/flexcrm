"""Sync ONE Meta connection: poll its Page's lead forms and ingest new leads.

Decrypt the stored token → Graph client → for each leadgen form, pull leads created
after the stored per-form cursor → map → idempotent ingest → advance the cursor →
set connection status. Leads are committed per-record by the ingest; the cursor is
persisted at form/end so a mid-run crash just re-polls (idempotent via external_id).
On a Graph auth error (token revoked, code 190) the connection flips to
`needs_reauth` and polling stops for it until the admin re-pastes a token.

The per-org loop + advisory lock + manager notification live in jobs/meta_lead_sync.
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.core.crypto import decrypt_secret
from app.database.enums import LeadIndustry
from app.models.meta_connection import MetaConnection
from app.services.base import ServiceBase
from app.services.lead_ingest import LeadIngestService
from app.services.meta_graph import MetaGraphClient, MetaGraphError
from app.services.meta_mapper import map_meta_lead


class MetaSyncService(ServiceBase):
    def __init__(self, session):
        super().__init__(session)
        self.ingest = LeadIngestService(session)

    def _mark_error(self, connection: MetaConnection, exc: MetaGraphError) -> None:
        connection.status = "needs_reauth" if exc.is_auth_error else "error"
        connection.status_detail = str(exc)[:500]
        connection.last_synced_at = datetime.now(UTC)

    async def sync_connection(self, connection: MetaConnection, *, organization_id: UUID) -> dict:
        """Poll + ingest for one connection. Returns {forms, created, skipped}."""
        stats = {"forms": 0, "created": 0, "skipped": 0}

        try:
            token = decrypt_secret(connection.token_encrypted)
        except Exception:
            connection.status = "error"
            connection.status_detail = "Stored token could not be decrypted."
            connection.last_synced_at = datetime.now(UTC)
            await self.commit()
            return stats

        try:
            industry = LeadIndustry(connection.default_industry)
        except ValueError:
            connection.status = "error"
            connection.status_detail = f"Unknown industry '{connection.default_industry}'."
            connection.last_synced_at = datetime.now(UTC)
            await self.commit()
            return stats

        client = MetaGraphClient(token)
        try:
            forms = await client.list_leadgen_forms(connection.page_id)
        except MetaGraphError as exc:
            self._mark_error(connection, exc)
            await self.commit()
            return stats

        cursors = dict(connection.form_cursors or {})
        for form in forms:
            form_id = str(form.get("id") or "")
            if not form_id:
                continue
            stats["forms"] += 1
            since = cursors.get(form_id)
            max_seen = since or 0
            try:
                async for lead in client.iter_form_leads(form_id, since_unix=since):
                    external_id, c_unix, fields = map_meta_lead(
                        lead, connection.field_map, provider=connection.provider
                    )
                    if not external_id:
                        continue
                    _, created = await self.ingest.ingest_lead(
                        organization_id=organization_id,
                        actor_id=connection.integration_user_id,
                        industry=industry,
                        source_provider=connection.provider,
                        external_id=external_id,
                        fields=fields,
                    )
                    stats["created" if created else "skipped"] += 1
                    if c_unix and c_unix > max_seen:
                        max_seen = c_unix
            except MetaGraphError as exc:
                # Persist progress on this form, then flag the connection and stop.
                if max_seen:
                    connection.form_cursors = {**cursors, form_id: max_seen}
                self._mark_error(connection, exc)
                await self.commit()
                return stats
            if max_seen and max_seen != since:
                cursors[form_id] = max_seen

        connection.form_cursors = cursors
        connection.status = "ok"
        connection.status_detail = None
        connection.last_synced_at = datetime.now(UTC)
        await self.commit()
        return stats
