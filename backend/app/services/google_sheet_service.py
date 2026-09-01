"""Google Sheets lead source: tenant connect/list/disconnect + a poll that ingests sheet rows.

The Sheet is the source, the CRM the destination. A single platform-owned service account
(app.core.google_sheets) reads a sheet the tenant has shared with it; the tenant only stores the Sheet
ID (in `external_account_id`). Rows follow the Meta lead pattern → `meta_sheet_mapper.map_sheet_row` →
`LeadIngestService.ingest_lead` (idempotent on external_id, so re-polling the whole sheet is safe). No
token / no public route — this is a PULL provider, unlike the 99acres push connector.
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.core.exceptions import NotFoundError, ValidationError
from app.core.google_sheets import SheetAccessError, SheetNotConfigured, read_rows, verify_access
from app.core.logging import get_logger
from app.core.tenancy import bypass, current_org
from app.database.enums import LeadIndustry
from app.models.lead_source_connection import LeadSourceConnection
from app.models.organization import Organization
from app.services.base import ServiceBase
from app.services.lead_ingest import LeadIngestService
from app.services.meta_sheet_mapper import map_sheet_row
from app.services.users import UserService

logger = get_logger(__name__)

_PROVIDER = "google_sheets"


class GoogleSheetService(ServiceBase):
    def __init__(self, session):
        super().__init__(session)
        self.ingest = LeadIngestService(session)

    async def _org(self) -> Organization:
        org_id = current_org(self.session)
        org = (
            await self.session.execute(select(Organization).where(Organization.id == org_id))
        ).scalar_one_or_none()
        if org is None:
            raise NotFoundError("Organization not found.")
        return org

    # --- tenant-facing ------------------------------------------------------

    async def connect(self, *, sheet_id: str, label: str | None, actor_id: UUID) -> LeadSourceConnection:
        """Verify the SA can read the sheet, then store the connection (sheet id in
        external_account_id). Raises ValidationError with a tenant-friendly message on failure."""
        sheet_id = (sheet_id or "").strip()
        if not sheet_id:
            raise ValidationError("A Google Sheet ID is required.")
        if len(sheet_id) > 64:
            raise ValidationError("That doesn't look like a Sheet ID — paste just the ID from the URL.")
        org = await self._org()
        industry = org.business_type
        if industry is None:
            raise ValidationError("This organization has no business type set; cannot connect.")
        try:
            verify_access(sheet_id)
        except SheetNotConfigured as exc:
            raise ValidationError("Google Sheets is not configured on the server yet — contact support.") from exc
        except SheetAccessError as exc:
            raise ValidationError(str(exc)) from exc

        integration_user = await UserService(self.session).get_or_create_integration_user(
            organization_id=org.id, business_type=industry
        )
        conn = LeadSourceConnection(
            provider=_PROVIDER,
            token_hash=None,  # pull provider: no URL token / public route
            external_account_id=sheet_id,
            label=label,
            default_industry=industry.value,
            integration_user_id=integration_user.id,
            status="ok",
            is_active=True,
            created_by_id=actor_id,
            updated_by_id=actor_id,
        )
        self.session.add(conn)
        await self.commit()
        return conn

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
                    LeadSourceConnection.provider == _PROVIDER,
                    LeadSourceConnection.is_deleted.is_(False),
                )
            )
        ).scalar_one_or_none()
        if conn is None:
            raise NotFoundError("Connection not found.")
        conn.is_deleted = True
        conn.is_active = False
        conn.updated_by_id = actor_id
        await self.commit()

    # --- poll side ----------------------------------------------------------

    async def sync_connection(self, conn: LeadSourceConnection, *, organization_id: UUID) -> dict[str, int]:
        """Read the sheet + ingest each row. Idempotent (ingest dedupes on external_id), so a full
        re-read is safe. Never raises — one bad row/sheet can't abort the poll."""
        stats = {"rows": 0, "created": 0, "duplicate": 0, "ignored": 0}
        # Snapshot scalars up-front: ingest commits/rolls back per row and can EXPIRE the ORM `conn`,
        # so using plain values avoids a MissingGreenlet lazy-load mid-loop (mirrors meta_lead_sync).
        conn_id = conn.id
        sheet_id = conn.external_account_id
        default_industry = conn.default_industry
        integration_user_id = conn.integration_user_id
        if not sheet_id:
            return stats
        try:
            rows = read_rows(sheet_id)
        except SheetNotConfigured:
            return stats  # feature not configured on the server; nothing to do
        except SheetAccessError as exc:
            await self._set_status(conn_id, "error", str(exc)[:500])
            return stats

        industry = await self._industry_for(default_industry, organization_id)
        actor_id = integration_user_id
        if actor_id is None:
            actor_id = (
                await UserService(self.session).get_or_create_integration_user(
                    organization_id=organization_id, business_type=industry
                )
            ).id

        created_any = False
        for row in rows:
            stats["rows"] += 1
            external_id, fields = map_sheet_row(row)
            if not external_id or not (fields.get("contact_phone") or fields.get("contact_email")):
                stats["ignored"] += 1
                continue
            try:
                _lead, created = await self.ingest.ingest_lead(
                    organization_id=organization_id,
                    actor_id=actor_id,
                    industry=industry,
                    source_provider=_PROVIDER,
                    external_id=external_id,
                    fields=fields,
                )
            except Exception:  # noqa: BLE001 — one bad row must not abort the sheet
                await self.session.rollback()
                logger.warning("google_sheet row ingest failed (org %s)", organization_id, exc_info=True)
                stats["ignored"] += 1
                continue
            if created:
                stats["created"] += 1
                created_any = True
            else:
                stats["duplicate"] += 1

        await self._set_status(conn_id, "ok", None, touch_lead=created_any)
        return stats

    async def _set_status(self, conn_id: UUID, status: str, detail: str | None, *, touch_lead: bool = False) -> None:
        conn = (
            await self.session.execute(
                select(LeadSourceConnection).where(LeadSourceConnection.id == conn_id)
            )
        ).scalar_one_or_none()
        if conn is None:
            return
        conn.status = status
        conn.status_detail = detail
        if touch_lead:
            conn.last_lead_at = datetime.now(UTC)
        await self.commit()

    async def _industry_for(self, default_industry: str | None, organization_id: UUID) -> LeadIndustry:
        if default_industry:
            try:
                return LeadIndustry(default_industry)
            except ValueError:
                pass
        with bypass(self.session):
            org = (
                await self.session.execute(select(Organization).where(Organization.id == organization_id))
            ).scalar_one_or_none()
        if org is not None and org.business_type is not None:
            return org.business_type
        return LeadIndustry.real_estate
