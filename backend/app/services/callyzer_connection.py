"""Tenant-facing Callyzer connection management + the poll/ingest sync.

Connect: the admin pastes their Callyzer API token; we probe it (a 1-record
callHistory call), encrypt it (app/core/crypto.py) and store the single per-tenant
connection. Sync: poll callHistory since the last watermark and upsert `ExternalCall`
rows (idempotent on provider+external_id). All operations run in the caller's tenant
schema (both tables are tenant-scoped). The token is never returned.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select

from app.core.crypto import decrypt_secret, encrypt_secret
from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.core.tenancy import current_org
from app.models.callyzer_connection import CallyzerConnection
from app.models.external_call import ExternalCall
from app.models.organization import Organization
from app.models.user import User
from app.schemas.callyzer import CallyzerConnectRequest
from app.services.base import ServiceBase
from app.services.callyzer_client import CallyzerClient, CallyzerError

logger = get_logger(__name__)

_PROVIDER = "callyzer"
# How far back to pull on the very first sync (no watermark yet).
_FIRST_SYNC_DAYS = 7
# Re-fetch a day of overlap each run so a boundary call isn't missed.
_OVERLAP_DAYS = 1
# Callyzer returns call_date/call_time (and reminder_date/time) in the ACCOUNT's local
# timezone, NOT UTC — the sandbox stamps records "... IST" and ignores a Time-Zone header.
# FlexCRM is an India-only product (see frontend formatDateTime), so treat these wall-clock
# strings as IST (a fixed +5:30, no DST) and let the timestamptz column store the true instant.
_CALLYZER_TZ = timezone(timedelta(hours=5, minutes=30))


def normalize_phone_key(number: object) -> str | None:
    """Last-10 digits of a phone number — the tenant-agnostic match key.

    Callyzer sends the country code separately (or embedded), and leads are stored
    free-text, so comparing the last 10 digits makes +91/0-prefixed/plain numbers
    all match. Returns None when there are no digits.
    """
    digits = re.sub(r"\D", "", str(number or ""))
    if not digits:
        return None
    return digits[-10:]


def _first(rec: dict, *keys: str) -> object:
    """First non-None value among the given keys (tolerates the API's snake_case
    and the webhook's camelCase field names)."""
    for k in keys:
        if k in rec and rec[k] not in (None, ""):
            return rec[k]
    return None


def _parse_dt(value: object) -> datetime | None:
    """Parse a Callyzer date/time string into an aware datetime. Callyzer omits the tz
    but the values are the account's LOCAL wall-clock (IST) — tag them _CALLYZER_TZ so the
    stored instant is correct. Accepts 'YYYY-MM-DD HH:MM:SS', ISO, or a date only."""
    if not value:
        return None
    s = str(value).strip().replace("/", "-")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=_CALLYZER_TZ)
        except ValueError:
            continue
    return None


def _call_at(rec: dict) -> datetime | None:
    date = _first(rec, "call_date", "callDate")
    time = _first(rec, "call_time", "callTime")
    if date and time and len(str(time)) <= 8:  # date + separate time
        return _parse_dt(f"{date} {time}")
    # callTime may already be a full "YYYY-MM-DD HH:MM:SS"
    return _parse_dt(_first(rec, "call_time", "callTime", "call_date", "callDate"))


def _to_int(value: object) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def map_call_record(rec: dict) -> dict:
    """Map a raw Callyzer call record → ExternalCall column values (provider-agnostic).
    Reads both API (snake_case) and webhook (camelCase) field names defensively."""
    client_number = _first(rec, "client_number", "number")
    return {
        "external_id": str(_first(rec, "id", "call_id") or ""),
        "client_number": client_number,
        "client_number_key": normalize_phone_key(client_number),
        "client_name": _first(rec, "client_name", "name"),
        "emp_number": _first(rec, "emp_number", "employeeNumber"),
        "emp_name": _first(rec, "emp_name", "employeeName"),
        "call_type": _first(rec, "call_type", "callType"),
        "call_method": _first(rec, "call_method", "callMethod"),
        "call_mode": _first(rec, "call_mode", "callMode"),
        "provider_lead_id": (
            str(_first(rec, "lead_id", "leadId")) if _first(rec, "lead_id", "leadId") else None
        ),
        "duration_seconds": _to_int(_first(rec, "duration")),
        "call_at": _call_at(rec),
        "note": _first(rec, "note"),
        "crm_status": _first(rec, "crm_status", "crmStatus"),
        "reminder_at": _parse_dt(_first(rec, "reminder_date", "reminderDate", "reminderTime")),
        "recording_url": _first(rec, "call_recording_url", "recordingURL", "recording_url"),
        "raw": rec,
    }


class CallyzerConnectionService(ServiceBase):
    async def _org(self) -> Organization:
        org_id = current_org(self.session)
        org = (
            await self.session.execute(select(Organization).where(Organization.id == org_id))
        ).scalar_one_or_none()
        if org is None:
            raise NotFoundError("Organization not found.")
        return org

    async def _find_connection(self) -> CallyzerConnection | None:
        """The tenant's connection INCLUDING soft-deleted (reconnect revives it)."""
        return (
            await self.session.execute(
                select(CallyzerConnection).order_by(CallyzerConnection.created_at.desc())
            )
        ).scalars().first()

    async def list_connections(self) -> list[CallyzerConnection]:
        rows = (
            await self.session.execute(
                select(CallyzerConnection)
                .where(CallyzerConnection.is_deleted.is_(False))
                .order_by(CallyzerConnection.created_at.desc())
            )
        ).scalars().all()
        return list(rows)

    async def _get(self, connection_id: UUID) -> CallyzerConnection:
        conn = (
            await self.session.execute(
                select(CallyzerConnection).where(
                    CallyzerConnection.id == connection_id,
                    CallyzerConnection.is_deleted.is_(False),
                )
            )
        ).scalar_one_or_none()
        if conn is None:
            raise NotFoundError("Callyzer connection not found.")
        return conn

    async def connect(self, req: CallyzerConnectRequest, *, actor_id: UUID) -> CallyzerConnection:
        """Validate + store the tenant's Callyzer token. Rejects a token that fails the
        probe. Reconnecting reuses/updates the single (possibly soft-deleted) row."""
        try:
            await CallyzerClient(req.token).probe()
        except CallyzerError as exc:
            reason = "invalid token" if exc.is_auth_error else "could not reach Callyzer"
            raise ValidationError(f"Could not connect ({reason}): {exc}")

        await self._org()  # ensure we're in a real tenant scope
        token_enc = encrypt_secret(req.token)
        conn = await self._find_connection()
        if conn is None:
            conn = CallyzerConnection(
                label=req.label,
                token_encrypted=token_enc,
                status="ok",
                created_by_id=actor_id,
                updated_by_id=actor_id,
            )
            self.session.add(conn)
        else:
            conn.is_deleted = False
            conn.deleted_at = None
            conn.is_active = True
            conn.label = req.label
            conn.token_encrypted = token_enc
            conn.status = "ok"
            conn.status_detail = None
            conn.updated_by_id = actor_id
        await self.commit()
        return conn

    async def disconnect(self, connection_id: UUID, *, actor_id: UUID) -> None:
        conn = await self._get(connection_id)
        conn.is_deleted = True
        conn.is_active = False
        conn.updated_by_id = actor_id
        await self.commit()

    # --- sync (poll) -------------------------------------------------------

    async def _user_phone_map(self, organization_id: UUID) -> dict[str, UUID]:
        """{last10(phone): user_id} for this org's users — to attribute a call to the
        FlexCRM user who made it (best-effort)."""
        rows = (
            await self.session.execute(
                select(User.id, User.phone).where(
                    User.organization_id == organization_id, User.phone.is_not(None)
                )
            )
        ).all()
        out: dict[str, UUID] = {}
        for user_id, phone in rows:
            key = normalize_phone_key(phone)
            if key:
                out.setdefault(key, user_id)
        return out

    async def sync_connection(
        self, conn: CallyzerConnection, *, organization_id: UUID
    ) -> dict[str, int]:
        """Poll callHistory since the watermark and upsert ExternalCall rows. Flips the
        connection to needs_reauth on an auth error; commits once at the end."""
        stats = {"fetched": 0, "created": 0, "updated": 0}
        try:
            token = decrypt_secret(conn.token_encrypted)
        except Exception:  # noqa: BLE001 — key rotated / corrupt cipher
            conn.status = "needs_reauth"
            conn.status_detail = "Stored token could not be decrypted."
            await self.commit()
            return stats

        now = datetime.now(UTC)
        # Poll by SYNC time (when Callyzer synced the record), so late-uploaded calls
        # are still caught. Overlap a day each run; seed a week back on first sync.
        synced_from = (
            (conn.last_synced_at - timedelta(days=_OVERLAP_DAYS))
            if conn.last_synced_at
            else now - timedelta(days=_FIRST_SYNC_DAYS)
        )

        user_map = await self._user_phone_map(organization_id)
        latest_call: datetime | None = conn.last_call_at

        client = CallyzerClient(token)
        try:
            async for rec in client.iter_call_history(synced_from=synced_from, synced_to=now):
                mapped = map_call_record(rec)
                if not mapped["external_id"]:
                    continue
                stats["fetched"] += 1
                mapped["user_id"] = user_map.get(normalize_phone_key(mapped["emp_number"]) or "")
                if mapped["call_at"] and (latest_call is None or mapped["call_at"] > latest_call):
                    latest_call = mapped["call_at"]

                existing = (
                    await self.session.execute(
                        select(ExternalCall).where(
                            ExternalCall.provider == _PROVIDER,
                            ExternalCall.external_id == mapped["external_id"],
                        )
                    )
                ).scalar_one_or_none()
                if existing is None:
                    self.session.add(ExternalCall(provider=_PROVIDER, **mapped))
                    stats["created"] += 1
                else:
                    for field, value in mapped.items():
                        setattr(existing, field, value)
                    stats["updated"] += 1
        except CallyzerError as exc:
            if exc.is_auth_error:
                conn.status = "needs_reauth"
                conn.status_detail = f"Token rejected: {exc}"[:500]
                await self.commit()
                return stats
            # Transient — keep the connection, retry next run.
            conn.status_detail = f"Sync error: {exc}"[:500]
            await self.commit()
            return stats

        conn.status = "ok"
        conn.status_detail = None
        conn.last_synced_at = now
        conn.last_call_at = latest_call
        await self.commit()
        return stats
