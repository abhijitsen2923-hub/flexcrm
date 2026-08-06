"""Sync ONE Meta connection: poll its Page's lead forms and ingest new leads.

Decrypt the stored token → Graph client → for each leadgen form, pull leads created
after the stored cursor → map → idempotent ingest → advance the cursor → set
connection status. Leads are committed per-record by the ingest; a form's cursor is
advanced ONLY after that form is fully drained, so a mid-pagination failure just re-polls
it from the last good point (idempotent via external_id) rather than skipping the older,
un-fetched leads — leads stream newest-first, so persisting the max-seen mid-run would
strand everything below it. An AUTH error (token revoked, code 190) flips the whole
connection to `needs_reauth` and stops polling until the admin re-pastes a token; a
non-auth error on one form is isolated — that form is skipped and the rest still poll.

Per-platform cursors: Facebook and Instagram leads arrive on the SAME leadgen form, so
the cursor is stored PER PLATFORM ({form_id: {"facebook": unix, "instagram": unix}}).
A lead's cursor advances only for the platform that is currently enabled — a disabled
platform's cursor is never touched, so enabling it later re-polls from where it left off
(or from the beginning if it was never enabled) and backfills the leads that arrived
while it was off. Re-scanning already-ingested leads is a no-op (external_id unique).

Known limitation (deferred): there is no intra-form checkpoint — a form is all-or-nothing
per run. A very large first-time backfill (since=None over full history) that repeatedly
hits a transient error at the same pagination depth never advances and re-scans its newest
pages each poll. New leads still ingest (they sit at the front of the newest-first stream);
only the deep-history tail can stall. A safe intra-form checkpoint needs oldest-first
paging, which Meta's /leads does not reliably offer — so this is left as-is.

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

# Platforms that share one Meta connection. Gating + cursors are keyed by these.
_PLATFORMS: tuple[str, ...] = ("facebook", "instagram")


def _form_platform_cursors(raw: object) -> dict[str, int]:
    """Normalize a stored per-form cursor into {platform: unix}. Tolerates the legacy
    single-int shape ({form_id: unix}) by applying it to both platforms, and ignores
    junk values so a malformed cursor can never crash the poll."""
    if isinstance(raw, dict):
        out: dict[str, int] = {}
        for p in _PLATFORMS:
            v = raw.get(p)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                out[p] = int(v)
        return out
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return {p: int(raw) for p in _PLATFORMS}
    return {}


class MetaSyncService(ServiceBase):
    def __init__(self, session):
        super().__init__(session)
        self.ingest = LeadIngestService(session)

    def _mark_error(self, connection: MetaConnection, exc: MetaGraphError) -> None:
        connection.status = "needs_reauth" if exc.is_auth_error else "error"
        connection.status_detail = str(exc)[:500]
        connection.last_synced_at = datetime.now(UTC)

    async def sync_connection(
        self,
        connection: MetaConnection,
        *,
        organization_id: UUID,
        allowed_platforms: set[str] | None = None,
    ) -> dict:
        """Poll + ingest for one connection. `allowed_platforms` (a subset of
        {"facebook","instagram"}) gates which platform's leads are ingested — FB and
        IG share one connection, so this honours the per-platform admin toggles.
        None = ingest all. Returns {forms, created, skipped, filtered}."""
        allowed = allowed_platforms
        active_platforms = (
            _PLATFORMS if allowed is None else tuple(p for p in _PLATFORMS if p in allowed)
        )
        stats = {"forms": 0, "created": 0, "skipped": 0, "filtered": 0}
        if not active_platforms:
            # Nothing enabled — don't poll (the job already skips such orgs; defensive).
            return stats

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
        # A non-auth Graph error on one form must not starve the others — record it and
        # keep polling the rest, then surface it as the connection status at the end. An
        # AUTH error is different: the token is bad for every form, so it stops the run.
        last_error: MetaGraphError | None = None
        for form in forms:
            form_id = str(form.get("id") or "")
            if not form_id:
                continue
            stats["forms"] += 1
            # Per-platform cursors on this form. Query from the OLDEST active-platform
            # cursor (None = never polled → fetch all history) so a newly-enabled
            # platform backfills; leads for platforms we won't ingest are re-scanned
            # cheaply and dropped without touching their cursor.
            form_cur = _form_platform_cursors(cursors.get(form_id))
            active_cur = [form_cur.get(p) for p in active_platforms]
            since = None if any(c is None for c in active_cur) else min(active_cur)
            new_max = dict(form_cur)  # disabled platforms' cursors carried through untouched
            try:
                async for lead in client.iter_form_leads(form_id, since_unix=since):
                    external_id, c_unix, fields = map_meta_lead(
                        lead, connection.field_map, provider=connection.provider
                    )
                    # FB and IG arrive on the same form; map source → platform and gate.
                    platform = "instagram" if fields.get("source") == "Instagram" else "facebook"
                    is_active = platform in active_platforms
                    # Advance ONLY the enabled platform's cursor (even for blank/filtered
                    # leads of that platform, so we don't re-scan them) — never a disabled
                    # platform's, so enabling it later re-polls from where it left off.
                    if is_active and c_unix is not None:
                        prev = new_max.get(platform)
                        if prev is None or c_unix > prev:
                            new_max[platform] = c_unix
                    if not external_id:
                        continue
                    if not is_active:
                        stats["filtered"] += 1
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
            except MetaGraphError as exc:
                # Never persist this form's partial progress. Leads stream newest-first, so
                # a mid-pagination failure has only seen the newest page(s); advancing the
                # cursor to the max-seen would strand the older, un-fetched leads forever
                # (the Graph filter is a strict time_created > cursor). The interrupted form
                # keeps its stored cursor and re-polls from its last good point next time
                # (idempotent via external_id) — as this module's docstring promises.
                if exc.is_auth_error:
                    # Token is bad for the WHOLE connection — persist the forms that fully
                    # completed, flag needs_reauth, and stop.
                    connection.form_cursors = dict(cursors)
                    self._mark_error(connection, exc)
                    await self.commit()
                    return stats
                # Transient/form-specific error: skip THIS form but keep polling the rest,
                # so one bad form can't block every form after it in the list.
                last_error = exc
                continue
            # Form fully consumed — only now is it safe to advance its cursor to the
            # max timestamp seen (we've fetched every older lead too, newest-first).
            if new_max:
                cursors[form_id] = new_max

        connection.form_cursors = cursors
        if last_error is not None:
            # One or more forms failed (non-auth); report it, but keep the cursors we did
            # advance for the forms that succeeded. The failed form(s) retry next poll.
            self._mark_error(connection, last_error)
        else:
            connection.status = "ok"
            connection.status_detail = None
            connection.last_synced_at = datetime.now(UTC)
        await self.commit()
        return stats
