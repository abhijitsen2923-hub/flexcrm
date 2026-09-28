"""Each tenant's own lead-campaign list: seeding, name resolution for every lead write path, manager tools.

- The list is per tenant (tenant schema) and starts from the tenant's OWN existing lead campaigns — nothing is
  hard-coded or shared across tenants.
- `resolve()` maps any incoming spelling (form, API, CSV, sheet, Meta, …) to the canonical campaign name:
  case/extra-space variants and merged/renamed old spellings (aliases) match automatically. Unknown names are
  created for managers, uploads and integrations (the latter two flagged `needs_review`); anyone else gets a
  422 with the reason `unknown_campaign`.
- Managers merge / rename / clear / (de)activate campaigns; lead rows are rewritten and the old spelling is
  remembered as an alias so it never comes back as a separate campaign.
- Everything fails OPEN while the tables don't exist yet (tenant migrations run in the background after
  boot): writes keep the cleaned raw value, reads fall back to plain matching.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError, ProgrammingError, SQLAlchemyError

from app.core.campaign_names import campaign_key, clean_display, closest_matches, suggest_merges
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.core.tenancy import current_org
from app.models.campaign import Campaign, CampaignAlias
from app.models.lead import Lead
from app.services.base import ServiceBase
from app.services.realtime import realtime_manager

logger = get_logger(__name__)

_INGEST_SOURCES = {"google_sheets": "sheet", "facebook": "meta", "instagram": "meta"}
_MAX_MERGE_SOURCES = 50
RACE_MESSAGE = "That campaign was just changed by someone else — refresh and try again."
# The list-reading GETs re-sync at most this often per tenant (per instance): the sync scans the tenant's
# leads, and every Leads page load / form open reads the list. Writes resolve names themselves.
_SYNC_INTERVAL_S = 300.0
_last_sync: dict[str, float] = {}
_LOCK_CONFLICT_STATES = {"40P01", "40001", "55P03"}  # deadlock, serialization failure, lock not available


def is_missing_table(exc: Exception) -> bool:
    """True when the campaign tables aren't there yet (tenant migration still running)."""
    orig = getattr(exc, "orig", None)
    if getattr(orig, "sqlstate", None) == "42P01" or getattr(orig, "pgcode", None) == "42P01":
        return True
    message = str(exc).lower()
    return "no such table" in message or (
        "does not exist" in message and ("campaigns" in message or "campaign_aliases" in message)
    )


def is_lock_conflict(exc: Exception) -> bool:
    """A deadlock / lock timeout with a concurrent campaign change — the caller should answer 409, not 500."""
    orig = getattr(exc, "orig", None)
    state = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    return state in _LOCK_CONFLICT_STATES


class CampaignRejected(ValidationError):
    """422 for a campaign this writer may not use (unknown / inactive). `detail` uses FastAPI's field-error
    list shape, which every client renders — including tabs still running an older frontend, which would
    otherwise show only a generic "some information looks incorrect". `str(exc)` is the plain message."""

    def __init__(self, message: str, *, reason: str, **extra: object) -> None:
        super().__init__(message, extra={"field": "campaign", "reason": reason, **extra})
        self.detail = [{"loc": ["body", "campaign"], "msg": message, "type": f"value_error.{reason}"}]  # type: ignore[assignment]


@dataclass(frozen=True)
class CampaignWritePolicy:
    """How a write path may treat a campaign name it doesn't know yet."""

    allow_create: bool
    source: str
    needs_review: bool
    allow_inactive: bool
    actor_id: UUID | None

    @classmethod
    def manual(cls, *, can_manage: bool, actor_id: UUID | None) -> CampaignWritePolicy:
        # New Lead form / API: only a campaign manager may add a name (or use a deactivated one).
        return cls(can_manage, "manual", False, can_manage, actor_id)

    @classmethod
    def imported(cls, *, can_manage: bool, actor_id: UUID | None) -> CampaignWritePolicy:
        # CSV upload: never reject a row over its campaign — add it, flagged for review unless a manager uploaded.
        return cls(True, "import", not can_manage, True, actor_id)

    @classmethod
    def ingest(cls, provider: str | None, actor_id: UUID | None) -> CampaignWritePolicy:
        # Sheet / Meta / other integrations: external data is never rejected; new names wait for review.
        return cls(True, _INGEST_SOURCES.get(provider or "", "integration"), True, True, actor_id)


class CampaignService(ServiceBase):
    # ---- internal reads -------------------------------------------------------------------------------

    async def _lead_spellings(self) -> list[tuple[str, int]]:
        """Every distinct stored campaign spelling on live leads, with its lead count."""
        rows = await self.session.execute(
            select(Lead.campaign, func.count())
            .where(Lead.is_deleted.is_(False), Lead.campaign.is_not(None))
            .group_by(Lead.campaign)
        )
        return [(value, count) for value, count in rows if value is not None]

    async def _maps(self) -> tuple[dict[str, Campaign], dict[str, CampaignAlias], dict[UUID, Campaign]]:
        campaigns = list((await self.session.execute(select(Campaign))).scalars().all())
        aliases = list((await self.session.execute(select(CampaignAlias))).scalars().all())
        by_id = {c.id: c for c in campaigns}
        return {c.name_key: c for c in campaigns}, {a.alias_key: a for a in aliases}, by_id

    async def _find_by_key(self, key: str) -> Campaign | None:
        """The campaign a key names — by its name, else via a remembered old spelling. The alias lookup is ONE
        statement joined to its campaign, so a concurrent merge (which moves aliases and deletes the source in
        one commit) is seen entirely before or entirely after. Fresh rows (populate_existing): long sessions
        (sheet sync, CSV import) must not reuse a stale identity-map copy after a rename."""
        campaign = (
            await self.session.execute(
                select(Campaign).where(Campaign.name_key == key).execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if campaign is not None:
            return campaign
        return (
            await self.session.execute(
                select(Campaign)
                .join(CampaignAlias, CampaignAlias.campaign_id == Campaign.id)
                .where(CampaignAlias.alias_key == key)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()

    async def _add_missing_from_leads(self) -> None:
        """Add a campaign for every key on the tenant's leads that the list doesn't know (display = the most
        frequent spelling). This is how a tenant's list is seeded — from its own data only. The list is read
        BEFORE the leads, so a campaign a manager clears meanwhile isn't re-added from a stale lead snapshot."""
        names, aliases, _ = await self._maps()
        spellings = await self._lead_spellings()
        variants: dict[str, dict[str, int]] = {}
        for value, count in spellings:
            key = campaign_key(value)
            if not key or key in names or key in aliases:
                continue
            display = clean_display(value) or value
            variants.setdefault(key, {})
            variants[key][display] = variants[key].get(display, 0) + count
        for key, spelled in variants.items():
            display = sorted(spelled.items(), key=lambda item: (-item[1], item[0]))[0][0]
            try:
                async with self.session.begin_nested():
                    self.session.add(Campaign(name=display, name_key=key, source="existing", needs_review=False))
                    await self.session.flush()
            except IntegrityError:
                pass  # added concurrently by another request — fine
            except DBAPIError:
                # One odd value must not block seeding the rest (the savepoint already rolled it back).
                logger.warning("campaign seed skipped for one value", exc_info=True)

    # ---- sync + resolution (all write paths) ------------------------------------------------------------

    async def ensure_synced(self) -> None:
        """Idempotent: cover every campaign on the tenant's leads, and store ONE spelling per campaign —
        leads holding a case/space variant or a merged/renamed old spelling are rewritten to the canonical
        name (`updated_at` untouched, no broadcast). Caller commits."""
        await self._add_missing_from_leads()
        names, aliases, by_id = await self._maps()
        spellings = await self._lead_spellings()  # after the list, for the same reason as above
        rewrites: dict[str, list[str]] = {}
        blanks: list[str] = []
        for value, _count in spellings:
            key = campaign_key(value)
            if not key:
                blanks.append(value)
                continue
            target = names.get(key) or (by_id.get(aliases[key].campaign_id) if key in aliases else None)
            if target is not None and value != target.name:
                rewrites.setdefault(target.name, []).append(value)
        if not rewrites and not blanks:
            return
        try:
            async with self.session.begin_nested():
                for canonical, stale in rewrites.items():
                    await self._rewrite_leads(stale, canonical, keep_audit=True)
                if blanks:
                    await self._rewrite_leads(blanks, None, keep_audit=True)
        except SQLAlchemyError:
            # e.g. a deadlock with a concurrent merge — the next call retries; never fail the request
            logger.warning("campaign canonicalisation skipped", exc_info=True)

    async def _sync_if_due(self) -> None:
        """ensure_synced for the list-reading GETs: always while the tenant's list is empty (first use seeds
        it), otherwise at most every _SYNC_INTERVAL_S per tenant on this instance."""
        tenant = str(current_org(self.session) or self.session.info.get("schema_name") or "")
        empty = (await self.session.execute(select(Campaign.id).limit(1))).first() is None
        last = _last_sync.get(tenant)
        if not empty and last is not None and time.monotonic() - last < _SYNC_INTERVAL_S:
            return
        await self.ensure_synced()
        await self.commit()
        _last_sync[tenant] = time.monotonic()
    async def resolve(self, raw: object, policy: CampaignWritePolicy) -> str | None:
        """Canonical campaign name for an incoming value (None for blank). Raises ValidationError (422) when
        `policy` doesn't allow a new or deactivated name. Fails open if the tables don't exist yet."""
        cleaned = clean_display(raw)
        if cleaned is None:
            return None
        key = campaign_key(cleaned)
        try:
            async with self.session.begin_nested():
                if (await self.session.execute(select(Campaign.id).limit(1))).first() is None:
                    await self._add_missing_from_leads()  # first use in this tenant: seed from its own leads
                campaign = await self._find_by_key(key)
                if campaign is None:
                    if not policy.allow_create:
                        await self._reject_unknown(cleaned)
                    campaign = Campaign(
                        name=cleaned,
                        name_key=key,
                        source=policy.source,
                        needs_review=policy.needs_review,
                        is_active=True,
                        created_by_id=policy.actor_id,
                        updated_by_id=policy.actor_id,
                    )
                    self.session.add(campaign)
                    await self.session.flush()
                elif not campaign.is_active and not policy.allow_inactive:
                    raise CampaignRejected(
                        f"'{campaign.name}' is inactive — pick an active campaign, or ask a manager to reactivate it.",
                        reason="inactive_campaign",
                    )
                return campaign.name
        except IntegrityError:
            # the same new name was added concurrently — use the winner
            campaign = await self._find_by_key(key)
            if campaign is not None:
                return campaign.name
            raise
        except (ProgrammingError, OperationalError) as exc:
            if is_missing_table(exc):
                logger.warning("campaign tables not ready — keeping the typed campaign as-is")
                return cleaned
            raise

    async def _reject_unknown(self, cleaned: str) -> None:
        active = list(
            (await self.session.execute(select(Campaign.name).where(Campaign.is_active.is_(True)))).scalars()
        )
        hints = closest_matches(cleaned, active)
        hint = f" Did you mean '{hints[0]}'?" if hints else ""
        raise CampaignRejected(
            f"'{cleaned}' isn't in your campaign list. Pick one from the list, or ask a manager to add it.{hint}",
            reason="unknown_campaign",
            suggestions=hints,
        )

    # ---- reads for the leads list ----------------------------------------------------------------------

    async def filter_values(self, raw: str) -> list[str]:
        """Stored spellings that mean the same campaign as `raw` — the canonical name plus remembered old
        spellings — so filtering by any variant finds all its leads (→ an index-friendly IN list)."""
        cleaned = clean_display(raw)
        if cleaned is None:
            return [raw] if raw else []
        try:
            async with self.session.begin_nested():
                campaign = await self._find_by_key(campaign_key(cleaned))
                if campaign is None:
                    return [raw]
                old = list(
                    (
                        await self.session.execute(
                            select(CampaignAlias.alias).where(CampaignAlias.campaign_id == campaign.id)
                        )
                    ).scalars()
                )
        except (ProgrammingError, OperationalError) as exc:
            if is_missing_table(exc):
                return [raw]
            raise
        return list(dict.fromkeys(v for v in (campaign.name, *old, raw, cleaned) if v))

    async def canonical_names(self, values: list[str]) -> list[str]:
        """Distinct stored values → their canonical names, one per campaign, sorted case-insensitively."""
        try:
            async with self.session.begin_nested():
                names, aliases, by_id = await self._maps()
        except (ProgrammingError, OperationalError) as exc:
            if not is_missing_table(exc):
                raise
            names, aliases, by_id = {}, {}, {}
        out: dict[str, str] = {}
        for value in values:
            key = campaign_key(value)
            if not key:
                continue
            campaign = names.get(key) or (by_id.get(aliases[key].campaign_id) if key in aliases else None)
            name = campaign.name if campaign is not None else (clean_display(value) or value)
            out.setdefault(campaign_key(name), name)
        return sorted(out.values(), key=str.lower)

    # ---- manager screen ---------------------------------------------------------------------------------

    async def list_options(self, *, include_inactive: bool) -> list[Campaign]:
        await self._sync_if_due()
        query = select(Campaign)
        if not include_inactive:
            query = query.where(Campaign.is_active.is_(True))
        rows = (await self.session.execute(query)).scalars().all()
        return sorted(rows, key=lambda c: c.name.lower())

    async def overview(self) -> dict:
        """Every campaign with its lead count and remembered spellings, plus merge suggestions."""
        await self._sync_if_due()
        spellings = await self._lead_spellings()
        names, aliases, by_id = await self._maps()
        counts: dict[UUID, int] = {}
        for value, count in spellings:
            key = campaign_key(value)
            campaign = names.get(key) or (by_id.get(aliases[key].campaign_id) if key in aliases else None)
            if campaign is not None:
                counts[campaign.id] = counts.get(campaign.id, 0) + count
        alias_rows: dict[UUID, list[CampaignAlias]] = {}
        for alias in aliases.values():
            alias_rows.setdefault(alias.campaign_id, []).append(alias)
        items = [
            {
                "campaign": campaign,
                "lead_count": counts.get(campaign.id, 0),
                "aliases": sorted(alias_rows.get(campaign.id, []), key=lambda a: a.alias.lower()),
            }
            for campaign in sorted(by_id.values(), key=lambda c: c.name.lower())
        ]
        # Pure CPU (pairwise name comparison) — keep it off the event loop.
        suggestions = await asyncio.to_thread(
            suggest_merges, [(str(item["campaign"].id), item["campaign"].name, item["lead_count"]) for item in items]
        )
        return {"items": items, "suggestions": suggestions}

    async def create(self, name: str, *, actor_id: UUID) -> Campaign:
        cleaned = clean_display(name)
        if cleaned is None:
            raise ValidationError("Campaign name can't be empty.", extra={"field": "name"})
        await self._ensure_key_free(campaign_key(cleaned))
        campaign = Campaign(
            name=cleaned, name_key=campaign_key(cleaned), source="manual", needs_review=False,
            is_active=True, created_by_id=actor_id, updated_by_id=actor_id,
        )
        self.session.add(campaign)
        await self.commit()
        await self._broadcast(0, "campaign_create")
        return campaign

    async def rename(self, campaign_id: UUID, name: str, *, actor_id: UUID) -> tuple[Campaign, int]:
        cleaned = clean_display(name)
        if cleaned is None:
            raise ValidationError("Campaign name can't be empty.", extra={"field": "name"})
        (campaign,) = await self._lock([campaign_id])
        new_key, old_key, old_name = campaign_key(cleaned), campaign.name_key, campaign.name
        own_keys = {old_key} | {a.alias_key for a in await self._aliases_of([campaign.id])}
        if new_key != old_key:
            other = (
                await self.session.execute(select(Campaign).where(Campaign.name_key == new_key))
            ).scalar_one_or_none()
            if other is not None:
                raise ConflictError(
                    f"'{other.name}' already exists — merge into it instead.",
                    extra={"reason": "name_exists", "conflict_campaign_id": str(other.id), "is_active": other.is_active},
                )
            alias = (
                await self.session.execute(select(CampaignAlias).where(CampaignAlias.alias_key == new_key))
            ).scalar_one_or_none()
            if alias is not None and alias.campaign_id != campaign.id:
                raise ConflictError(
                    f"'{cleaned}' is already an old spelling of another campaign — merge instead.",
                    extra={"reason": "alias_of_other", "conflict_campaign_id": str(alias.campaign_id)},
                )
            if alias is not None:  # renaming back to one of its own old spellings
                await self.session.delete(alias)
            self.session.add(
                CampaignAlias(campaign_id=campaign.id, alias=old_name, alias_key=old_key, kind="rename", created_by_id=actor_id)
            )
        campaign.name, campaign.name_key = cleaned, new_key
        campaign.needs_review = False
        campaign.updated_by_id = actor_id
        count = await self._rewrite_leads(await self._spellings_for(own_keys), cleaned, actor_id=actor_id)
        await self.commit()
        await self._after_lead_change(count, "campaign_rename")
        return campaign, count

    async def merge(self, source_ids: list[UUID], target_id: UUID, *, actor_id: UUID) -> tuple[Campaign, int]:
        sources = list(dict.fromkeys(source_ids))
        if not sources:
            raise ValidationError("Pick at least one campaign to merge.")
        if len(sources) > _MAX_MERGE_SOURCES:
            raise ValidationError(f"Merge at most {_MAX_MERGE_SOURCES} campaigns at a time.")
        if target_id in sources:
            raise ValidationError("A campaign can't be merged into itself.")
        locked = {c.id: c for c in await self._lock([*sources, target_id])}
        target = locked[target_id]
        source_rows = [locked[i] for i in sources]
        source_aliases = await self._aliases_of(sources)
        keys = {c.name_key for c in source_rows} | {a.alias_key for a in source_aliases}
        count = await self._rewrite_leads(await self._spellings_for(keys), target.name, actor_id=actor_id)
        # Keep aliases flat: the sources' old spellings now point at the target, and each source name becomes one.
        await self.session.execute(
            update(CampaignAlias).where(CampaignAlias.campaign_id.in_(sources)).values(campaign_id=target.id)
        )
        for source in source_rows:
            self.session.add(
                CampaignAlias(campaign_id=target.id, alias=source.name, alias_key=source.name_key, kind="merge", created_by_id=actor_id)
            )
        await self.session.execute(delete(Campaign).where(Campaign.id.in_(sources)))
        target.needs_review = False
        target.updated_by_id = actor_id
        await self.commit()
        await self._after_lead_change(count, "campaign_merge")
        return target, count

    async def clear(self, campaign_id: UUID, *, actor_id: UUID) -> int:
        """Remove a (junk) campaign: its leads end up with no campaign, and it leaves the list."""
        (campaign,) = await self._lock([campaign_id])
        aliases = await self._aliases_of([campaign.id])
        keys = {campaign.name_key} | {a.alias_key for a in aliases}
        count = await self._rewrite_leads(await self._spellings_for(keys), None, actor_id=actor_id)
        await self.session.execute(delete(CampaignAlias).where(CampaignAlias.campaign_id == campaign.id))
        await self.session.execute(delete(Campaign).where(Campaign.id == campaign.id))
        await self.commit()
        await self._after_lead_change(count, "campaign_clear")
        return count

    async def set_flags(
        self, campaign_id: UUID, *, is_active: bool | None, reviewed: bool, actor_id: UUID
    ) -> Campaign:
        (campaign,) = await self._lock([campaign_id])
        if is_active is not None:
            campaign.is_active = is_active
        if reviewed:
            campaign.needs_review = False
        campaign.updated_by_id = actor_id
        await self.commit()
        await self._broadcast(0, "campaign_update")
        return campaign

    async def delete_alias(self, campaign_id: UUID, alias_id: UUID) -> None:
        alias = (
            await self.session.execute(
                select(CampaignAlias).where(CampaignAlias.id == alias_id, CampaignAlias.campaign_id == campaign_id)
            )
        ).scalar_one_or_none()
        if alias is None:
            raise NotFoundError("Old spelling not found.")
        await self.session.delete(alias)
        await self.commit()
        await self._broadcast(0, "campaign_update")

    async def read_row(self, campaign: Campaign) -> dict:
        """One campaign as the manager screen shows it (lead count + remembered spellings)."""
        aliases = await self._aliases_of([campaign.id])
        keys = {campaign.name_key} | {a.alias_key for a in aliases}
        count = sum(n for value, n in await self._lead_spellings() if campaign_key(value) in keys)
        return {"campaign": campaign, "lead_count": count, "aliases": sorted(aliases, key=lambda a: a.alias.lower())}

    # ---- mutation helpers -------------------------------------------------------------------------------

    async def _ensure_key_free(self, key: str) -> None:
        existing = (await self.session.execute(select(Campaign).where(Campaign.name_key == key))).scalar_one_or_none()
        if existing is not None:
            raise ConflictError(
                f"'{existing.name}' already exists."
                + ("" if existing.is_active else " It's inactive — reactivate it instead."),
                extra={"reason": "name_exists", "conflict_campaign_id": str(existing.id), "is_active": existing.is_active},
            )
        alias = (
            await self.session.execute(select(CampaignAlias).where(CampaignAlias.alias_key == key))
        ).scalar_one_or_none()
        if alias is not None:
            raise ConflictError(
                "That name is an old spelling of another campaign.",
                extra={"reason": "alias_of_other", "conflict_campaign_id": str(alias.campaign_id)},
            )

    async def _lock(self, ids: list[UUID]) -> list[Campaign]:
        """Row-lock the campaigns (in id order, so concurrent merges can't deadlock); a missing id means
        someone else merged/cleared it first → 409."""
        wanted = list(dict.fromkeys(ids))
        rows = (
            await self.session.execute(
                select(Campaign).where(Campaign.id.in_(wanted)).order_by(Campaign.id).with_for_update()
            )
        ).scalars().all()
        by_id = {c.id: c for c in rows}
        if len(by_id) != len(wanted):
            raise ConflictError(RACE_MESSAGE, extra={"reason": "stale"})
        return [by_id[i] for i in wanted]

    async def _aliases_of(self, campaign_ids: list[UUID]) -> list[CampaignAlias]:
        return list(
            (
                await self.session.execute(select(CampaignAlias).where(CampaignAlias.campaign_id.in_(campaign_ids)))
            ).scalars()
        )

    async def _spellings_for(self, keys: set[str]) -> list[str]:
        """Stored spellings (incl. not-yet-canonicalised variants) whose key is in `keys`."""
        return [value for value, _n in await self._lead_spellings() if campaign_key(value) in keys]

    async def _rewrite_leads(
        self, spellings: list[str], new_value: str | None, *, actor_id: UUID | None = None, keep_audit: bool = False
    ) -> int:
        if not spellings:
            return 0
        values: dict = {"campaign": new_value}
        if keep_audit:
            values["updated_at"] = Lead.updated_at  # automatic housekeeping: don't look like a user edit
        else:
            values["updated_by_id"] = actor_id
        result = await self.session.execute(
            update(Lead)
            .where(Lead.campaign.in_(spellings), Lead.is_deleted.is_(False))
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        return result.rowcount or 0

    async def _after_lead_change(self, count: int, reason: str) -> None:
        if count:
            await self.invalidate_reporting_cache()
        await self._broadcast(count, reason)

    async def _broadcast(self, count: int, reason: str) -> None:
        # One combined event: open Leads lists + the Campaign filter / Campaigns screen refresh.
        if count:
            await realtime_manager.broadcast({"event": "lead.updated", "payload": {"count": count, "reason": reason}})
        else:
            await realtime_manager.broadcast({"event": "campaign.updated", "payload": {"reason": reason}})
