"""Bulk CSV import for leads.

Same flow as `POST /leads` + `POST /leads/{id}/transitions`, but driven by
a CSV row instead of a JSON body. Each row produces a Lead in the caller's
org; if the row's `stage` column is anything other than the industry's
position-1 code, a synthetic transition is fired so:

  - the Lead lands at the requested stage,
  - the Stage History records `null → new_enquiry → <stage>`,
  - the existing auto-promotion side effects (Customer + SalesOrder +
    commission accrual) fire on `sold` rows for free.

Per-row errors don't abort the upload — the response carries counts and a
list of `(row_number, message)` problems so the user can fix the sheet
and re-import the failed rows.

Bulk-friendly: realtime events and the reporting-cache wipe are merged into one per request
(`bulk_side_effects`), duplicates are looked up for the whole request in one query, assignee emails are
resolved once each, and each assignee gets one summary notification per request. (The browser sends big files
as 50-row chunks, so that's once per chunk — still instead of once per row.) Row errors are plain sentences (no raw SQL/pydantic
text). Large files are sent by the browser in chunks (`row_offset` keeps row numbers matching the sheet).
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, NamedTuple
from uuid import UUID

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from app.core.currencies import DEFAULT_CURRENCY, allowed_currencies_for_org
from app.core.exceptions import AppException, ValidationError
from app.core.lead_csv import CsvColumn, import_columns_for
from app.core.lead_intent import normalize_intent
from app.core.logging import get_logger, request_id_context
from app.core.permissions import can_set_stage
from app.core.tenancy import current_org
from app.core.lead_normalize import (
    normalize_property_interest,
    normalize_property_type,
    normalize_source,
)
from app.database.enums import LeadIndustry, UserRole
from app.database.pipeline_seed import initial_stage_code
from app.services.campaigns import CampaignWritePolicy
from app.models.lead import Lead
from app.models.organization import Organization
from app.models.pipeline_stage import PipelineStage
from app.repositories.leads import LeadRepository
from app.repositories.users import UserRepository
from app.schemas.lead import LeadCreate
from app.schemas.stage_transition import StageTransitionCreate
from app.services.base import ServiceBase
from app.services.bulk_scope import bulk_side_effects
from app.services.leads import LeadService
from app.services.notifications import NotificationService
from app.services.stage_transitions import StageTransitionService

logger = get_logger(__name__)

_ROW_DB_ERROR = "Couldn't save this row — the database rejected one of its values. Check the row and upload it again."
_MAX_DUPLICATE_MATCHES = 5


def _canon_header(value: str | None) -> str:
    """Canonical header key: lowercased with all non-alphanumerics removed, so
    'Contact Name' / 'contact_name' / 'contact-name' / 'CONTACTNAME' collapse to one
    key and match."""
    return re.sub(r"[^a-z0-9]", "", (value or "").strip().lower())


# Split-name headers combined into contact_name when there's no single name column.
_FIRST_NAME_ALIASES = ("first_name", "first name", "firstname", "given name", "fname")
_LAST_NAME_ALIASES = ("last_name", "last name", "lastname", "surname", "family name", "lname")


# Column definitions (headers, aliases, parse kinds) live in app.core.lead_csv,
# keyed per business type, so the template / importer / exporter stay in sync.


class StageRef(NamedTuple):
    """Detached (code, name) snapshot of a PipelineStage row.

    Deliberately NOT the ORM object. The import loop calls `session.rollback()`
    when a row fails, and rollback EXPIRES every persistent instance. If the
    stage lookup held ORM objects, the next row's `stage.code` / `stage.name`
    read would fire a lazy refresh outside an await and raise MissingGreenlet
    ("greenlet_spawn has not been called") — turning one bad row into a failure
    for every remaining row in the file. Snapshotting to plain strings is the
    same defence the Meta jobs use for the same reason
    (see app/jobs/meta_lead_sync.py).
    """
    code: str
    name: str


@dataclass
class ImportRowError:
    row: int
    error: str


class _RowResult(NamedTuple):
    lead_number: int
    promoted: bool
    assignee_id: UUID | None
    stage_warning: str | None


def _decimal_limit(column_key: str) -> Decimal | None:
    """Largest magnitude the lead column can store (Numeric(12, 2) → < 10^10), so a too-large Value/Budget is a
    labelled row error rather than an unexplained database rejection."""
    column = Lead.__table__.c.get(column_key)
    precision = getattr(getattr(column, "type", None), "precision", None)
    scale = getattr(getattr(column, "type", None), "scale", None) or 0
    return Decimal(10) ** (precision - scale) if precision else None


def _is_blank_row(raw: dict) -> bool:
    """A row with no content in any cell (Excel often saves ",,,,," lines) — skipped, not an error."""
    for value in raw.values():
        cells = value if isinstance(value, list) else [value]  # extra cells beyond the header come as a list
        if any(cell is not None and str(cell).strip() for cell in cells):
            return False
    return True


def _app_error_text(exc: AppException) -> str:
    detail = exc.detail
    if isinstance(detail, list) and detail and isinstance(detail[0], dict):  # field-error list shape
        return str(detail[0].get("msg") or "This row has an invalid value.")
    return str(detail)


def _pydantic_error_text(exc: PydanticValidationError, headers: dict[str, str]) -> str:
    """'Email: value is not a valid email address…' — the sheet's column name, not the internal field."""
    parts = []
    for error in exc.errors()[:3]:
        loc = error.get("loc") or ()
        field_name = str(loc[0]) if loc else ""
        label = headers.get(field_name) or field_name.replace("_", " ").capitalize() or "Value"
        parts.append(f"{label}: {error.get('msg') or 'is invalid'}")
    return "; ".join(parts) or "This row has an invalid value."


@dataclass
class ImportDuplicate:
    """A row that matched an existing lead by email or phone."""
    row: int
    contact_name: str | None
    contact_email: str | None
    contact_phone: str | None
    matched: str          # existing lead numbers, e.g. "#89004, #89003"
    skipped: bool         # True when skip_duplicates dropped it; False = imported anyway


@dataclass
class ImportSummary:
    created: int = 0
    promoted: int = 0
    skipped: int = 0
    errors: list[ImportRowError] = field(default_factory=list)
    duplicates: list[ImportDuplicate] = field(default_factory=list)


class LeadImportService(ServiceBase):
    """CSV → leads. Reuses `LeadService` + `StageTransitionService` for parity
    with manual creation."""

    def __init__(self, session):
        super().__init__(session)
        self.lead_service = LeadService(session)
        self.transition_service = StageTransitionService(session)
        self.lead_repository = LeadRepository(session)
        self.user_repository = UserRepository(session)

    async def import_csv(
        self,
        file_bytes: bytes,
        *,
        actor_id: UUID,
        actor_role: UserRole,
        actor_business_type: LeadIndustry | None,
        skip_duplicates: bool = False,
        campaign_policy: CampaignWritePolicy | None = None,
        row_offset: int = 0,
    ) -> ImportSummary:
        """`row_offset`: data rows that came before this part of a file the browser sends in chunks, so
        reported row numbers still match the sheet."""
        try:
            text = file_bytes.decode("utf-8-sig")  # tolerate BOM from Excel exports
        except UnicodeDecodeError as exc:
            raise ValidationError("CSV must be UTF-8 encoded.") from exc

        # Auto-detect the delimiter — Excel exports semicolons (or tabs) in many
        # locales; whichever candidate appears most in the header line wins, comma
        # is the default + tie-break.
        first_line = next((ln for ln in text.splitlines() if ln.strip()), "")
        delimiter = max((",", ";", "\t", "|"), key=first_line.count)
        if first_line.count(delimiter) == 0:
            delimiter = ","
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        if reader.fieldnames is None:
            raise ValidationError("CSV is empty or has no header row.")

        # Resolve the vertical first — it determines which columns we accept
        # (e.g. Destination for travel, property/budget fields for real estate).
        org = await self._load_org_or_default_industry(actor_business_type)
        industry = org.business_type if org else actor_business_type
        if industry is None:
            raise ValidationError(
                "Cannot determine the import industry — your account has no business_type set."
            )

        columns = import_columns_for(industry)
        header_map = self._build_header_map(reader.fieldnames, columns)
        # Fallback: accept a split First name + Last name pair as the contact name.
        first_header = last_header = None
        if "contact_name" not in header_map:
            first_header = self._match_header(reader.fieldnames, _FIRST_NAME_ALIASES)
            last_header = self._match_header(reader.fieldnames, _LAST_NAME_ALIASES)
            if not first_header:
                raise ValidationError(
                    "CSV must include a `contact_name` column — accepted headers: Name, Contact, "
                    "Contact name, Full name (or a First name + Last name pair). Tip: use the "
                    "Download template button in the import dialog for the exact headers."
                )

        allowed_currencies = allowed_currencies_for_org(org) if org else [DEFAULT_CURRENCY]
        stage_lookup = await self._stage_lookup_for_industry(industry)
        initial_code = initial_stage_code(industry.value)

        summary = ImportSummary()
        headers = {col.key: col.header for col in columns}
        self._assignee_ids: dict[str, UUID | None] = {}

        # CSV row numbering starts at 2 (header is row 1) so the user can
        # cross-reference with their spreadsheet.
        prepared: list[tuple[int, dict[str, str | None]]] = []
        for offset, raw in enumerate(reader, start=2 + row_offset):
            if _is_blank_row(raw):
                continue
            row = {col.key: self._read_field(raw, header_map.get(col.key)) for col in columns}
            # Combine a split first/last name into contact_name when there's no
            # single name column (last name optional).
            if not row.get("contact_name") and first_header:
                first = self._read_field(raw, first_header) or ""
                last = (self._read_field(raw, last_header) or "") if last_header else ""
                combined = f"{first} {last}".strip()
                if combined:
                    row["contact_name"] = combined
            prepared.append((offset, row))

        def _keys(row: dict[str, str | None]) -> tuple[str | None, str | None]:
            email = (row.get("contact_email") or "").strip().lower() or None
            phone = re.sub(r"\D", "", row.get("contact_phone") or "") or None
            return email, phone

        # Duplicate detection for the whole file in one lookup (not a full-table scan per row). Leads created
        # by earlier rows of this file are added as we go, so in-file duplicates are still caught.
        all_keys = [_keys(row) for _, row in prepared]
        known = await self.lead_repository.duplicate_numbers(
            {email for email, _ in all_keys if email}, {phone for _, phone in all_keys if phone}
        )
        assigned: dict[UUID, int] = {}

        # One realtime event + one cache wipe for the whole import (not one per row).
        async with bulk_side_effects():
            for offset, row in prepared:
                email_norm, phone_digits = _keys(row)
                matched: list[int] = []
                for key in (f"e:{email_norm}" if email_norm else None, f"p:{phone_digits}" if phone_digits else None):
                    for number in known.get(key, []) if key else []:
                        if number not in matched:
                            matched.append(number)
                if matched:
                    matched.sort(reverse=True)
                    summary.duplicates.append(
                        ImportDuplicate(
                            row=offset,
                            contact_name=(row.get("contact_name") or "").strip() or None,
                            contact_email=(row.get("contact_email") or "").strip() or None,
                            contact_phone=(row.get("contact_phone") or "").strip() or None,
                            matched=", ".join(f"#{n}" for n in matched[:_MAX_DUPLICATE_MATCHES]),
                            skipped=skip_duplicates,
                        )
                    )
                    if skip_duplicates:
                        summary.skipped += 1
                        continue

                error: str | None = None
                try:
                    result = await self._import_row(
                        row,
                        columns=columns,
                        actor_id=actor_id,
                        actor_role=actor_role,
                        industry=industry,
                        initial_code=initial_code,
                        allowed_currencies=allowed_currencies,
                        stage_lookup=stage_lookup,
                        campaign_policy=campaign_policy,
                    )
                except AppException as exc:  # incl. our ValidationError — messages written for users
                    error = _app_error_text(exc)
                except PydanticValidationError as exc:
                    error = _pydantic_error_text(exc, headers)
                except DBAPIError:
                    logger.warning("CSV import row %s rejected by the database", offset, exc_info=True)
                    error = _ROW_DB_ERROR
                except Exception:  # noqa: BLE001 — surface unknown errors per-row, don't kill the batch
                    logger.exception("CSV import row %s failed", offset)
                    error = f"Couldn't import this row (unexpected error, reference {request_id_context.get()})."
                if error is not None:
                    summary.errors.append(ImportRowError(row=offset, error=error))
                    # Roll back any partial state from this row so the next row starts clean.
                    await self.session.rollback()
                    self.lead_service.forget_campaign_names()
                    continue

                summary.created += 1
                if result.promoted:
                    summary.promoted += 1
                if result.stage_warning:
                    summary.errors.append(ImportRowError(row=offset, error=result.stage_warning))
                if result.assignee_id is not None:
                    assigned[result.assignee_id] = assigned.get(result.assignee_id, 0) + 1
                for key in (f"e:{email_norm}" if email_norm else None, f"p:{phone_digits}" if phone_digits else None):
                    if key:
                        known.setdefault(key, []).insert(0, result.lead_number)

        await self._notify_assignees(assigned)
        return summary

    async def _notify_assignees(self, assigned: dict[UUID, int]) -> None:
        """One notification per assignee per request (a chunk, for big files — like bulk reassign), not one per lead."""
        if not assigned:
            return
        try:
            notifications = NotificationService(self.session)
            for user_id, count in assigned.items():
                await notifications.create_notification(
                    user_id=user_id,
                    message=f"{count} lead{'s' if count != 1 else ''} assigned to you (CSV import).",
                )
            await self.commit()
        except Exception:  # noqa: BLE001 — the leads are already saved; a missed nudge must not fail the import
            await self.session.rollback()
            logger.warning("CSV import: assignee notifications failed", exc_info=True)

    # --- per-row work ------------------------------------------------------

    async def _import_row(
        self,
        row: dict[str, str | None],
        *,
        columns: list[CsvColumn],
        actor_id: UUID,
        actor_role: UserRole,
        industry: LeadIndustry,
        initial_code: str,
        allowed_currencies: list[str],
        stage_lookup: dict[str, StageRef],
        campaign_policy: CampaignWritePolicy | None = None,
    ) -> _RowResult:
        contact_name = (row.get("contact_name") or "").strip()
        if not contact_name:
            raise ValidationError("contact_name is required.")
        # Primary phone is mandatory (all verticals); email is optional. Check
        # here for a clear per-row message instead of a raw pydantic error.
        if not (row.get("contact_phone") or "").strip():
            raise ValidationError("Phone is required.")

        currency = (row.get("currency") or DEFAULT_CURRENCY).strip().upper() or DEFAULT_CURRENCY
        if currency not in allowed_currencies:
            raise ValidationError(
                f"Currency '{currency}' is not enabled for this org. Allowed: {', '.join(allowed_currencies)}."
            )

        # Build the LeadCreate payload straight from the vertical's column
        # registry so vertical-specific fields (property_type, budget_*, …) map
        # through automatically. `stage` is handled separately via a transition.
        payload_kwargs: dict = {
            "industry": industry,
            "contact_name": contact_name,
            "title": (row.get("title") or "").strip() or contact_name,
            "currency": currency,
        }
        _handled = {"stage", "contact_name", "title", "currency", "owner_email"}
        intent_warning: str | None = None
        for col in columns:
            if col.key in _handled:
                continue
            raw_val = row.get(col.key)
            if col.kind == "decimal":
                default = Decimal("0") if col.key == "value" else None
                payload_kwargs[col.key] = self._parse_decimal(
                    raw_val, field=col.header, default=default, max_abs=_decimal_limit(col.key)
                )
            elif col.kind == "int":
                payload_kwargs[col.key] = self._parse_int(raw_val, field=col.header, default=0, lo=0, hi=100)
            elif col.kind == "date":
                payload_kwargs[col.key] = self._parse_date(raw_val)
            elif col.kind == "intent":
                # An existing sheet may already have an "Intent" column meaning something else — import the
                # lead anyway, not rated, and say so (never fail the row over it).
                try:
                    payload_kwargs[col.key] = normalize_intent(raw_val)
                except ValueError:
                    payload_kwargs[col.key] = None
                    intent_warning = (
                        f"{col.header} '{str(raw_val).strip()}' isn't High, Medium or Low — the lead was imported "
                        "without an intent."
                    )
            else:
                payload_kwargs[col.key] = raw_val or None

        # Snap free-text CSV values to the controlled dropdown labels so imported
        # rows line up with the UI's Source / Property Interest / Property type
        # selects. Unrecognised values pass through as free text (never rejected).
        # Campaign is NOT snapped here: create_lead maps it onto the tenant's own
        # campaign list (case/space variants + remembered old spellings).
        if "source" in payload_kwargs:
            payload_kwargs["source"] = normalize_source(payload_kwargs["source"])
        if industry == LeadIndustry.real_estate:
            if "interest" in payload_kwargs:
                payload_kwargs["interest"] = normalize_property_interest(payload_kwargs["interest"])
            if "property_type" in payload_kwargs:
                payload_kwargs["property_type"] = normalize_property_type(payload_kwargs["property_type"])

        # Resolve the optional assignee by email → a user in this workspace (once per email per import).
        owner_email = (row.get("owner_email") or "").strip().lower()
        if owner_email:
            if owner_email not in self._assignee_ids:
                owner = await self.user_repository.get_by_email(owner_email)
                org_id = current_org(self.session)
                valid = owner is not None and (org_id is None or owner.organization_id == org_id)
                self._assignee_ids[owner_email] = owner.id if valid else None
            if self._assignee_ids[owner_email] is None:
                raise ValidationError(
                    f"Assignee email '{owner_email}' does not match a user in your workspace."
                )
            payload_kwargs["assigned_to_id"] = self._assignee_ids[owner_email]

        payload = LeadCreate(**payload_kwargs)

        # Check the Stage BEFORE creating the lead, so an unknown or not-allowed stage is a plain row error
        # instead of a lead that exists while its row is reported as failed.
        target_stage = self._resolve_stage(row.get("stage"), stage_lookup, industry, default=initial_code)
        if target_stage.code != initial_code and not can_set_stage(actor_role, target_stage.code):
            raise ValidationError(
                f"Stage: your role can't set '{target_stage.name}'. Leave Stage empty, or ask a manager to import this row."
            )

        lead = await self.lead_service.create_lead(
            payload,
            actor_id=actor_id,
            actor_business_type=industry,
            assignment_source="import",
            campaign_policy=campaign_policy
            or CampaignWritePolicy.imported(can_manage=False, actor_id=actor_id),
            notify_assignee=False,  # one summary per assignee at the end of the import
            reload=False,
        )
        # Plain values: a rollback below would expire the ORM object.
        lead_id, lead_number, assignee_id = lead.id, lead.lead_number, lead.assigned_to_id

        was_promoted = False
        stage_warning: str | None = None
        if target_stage.code != initial_code:
            # Move the lead to the requested stage via the regular transition
            # service so all side effects (comment log, realtime broadcast,
            # auto-promotion on Sold) fire identically to manual moves.
            try:
                await self.transition_service.create_transition(
                    lead_id,
                    StageTransitionCreate(
                        to_stage_code=target_stage.code,
                        comment=f"Imported from CSV upload — initial stage set to {target_stage.name}.",
                        intent=payload.intent,
                    ),
                    actor_id=actor_id,
                    actor_role=actor_role,
                    intent_source="import",
                )
                was_promoted = target_stage.code == "sold"
            except Exception as exc:  # noqa: BLE001 — the lead is saved; report the stage, don't call it failed
                await self.session.rollback()
                reason = _app_error_text(exc) if isinstance(exc, AppException) else "it couldn't be applied"
                if not isinstance(exc, AppException):
                    logger.warning("CSV import: stage move failed for lead %s", lead_id, exc_info=True)
                stage_warning = (
                    f"Lead #{lead_number} was created at the first stage, but stage '{target_stage.name}' "
                    f"wasn't set: {reason}"
                )

        warning = " ".join(w for w in (intent_warning, stage_warning) if w) or None
        return _RowResult(lead_number, was_promoted, assignee_id, warning)

    # --- helpers -----------------------------------------------------------

    def _build_header_map(self, fieldnames: list[str], columns: list[CsvColumn]) -> dict[str, str]:
        """Map each registry column's key to the actual header present in the CSV.

        Both sides are reduced to a canonical key (lowercased, non-alphanumerics
        removed) so 'Contact Name' / 'contact_name' / 'contact-name' all match. The
        first matching alias wins.
        """
        normalised = {_canon_header(h): h for h in fieldnames if h}
        out: dict[str, str] = {}
        for col in columns:
            for alias in col.all_aliases():
                hit = normalised.get(_canon_header(alias))
                if hit is not None:
                    out[col.key] = hit
                    break
        return out

    def _match_header(self, fieldnames: list[str], aliases: tuple[str, ...]) -> str | None:
        """The actual CSV header matching any of `aliases` (canonical compare), else None."""
        normalised = {_canon_header(h): h for h in fieldnames if h}
        for alias in aliases:
            hit = normalised.get(_canon_header(alias))
            if hit is not None:
                return hit
        return None

    def _read_field(self, raw: dict[str, Any], header: str | None) -> str | None:
        if header is None:
            return None
        value = raw.get(header)
        if value is None:
            return None
        text = str(value).strip()
        return text if text else None

    def _parse_decimal(
        self, value: str | None, *, field: str, default: Decimal | None, max_abs: Decimal | None = None
    ) -> Decimal | None:
        if not value:
            return default
        try:
            parsed = Decimal(value.replace(",", ""))
        except (InvalidOperation, ValueError) as exc:
            raise ValidationError(f"{field} '{value}' is not a valid number.") from exc
        if not parsed.is_finite():
            raise ValidationError(f"{field} '{value}' is not a valid number.")
        if max_abs is not None and abs(parsed) >= max_abs:
            raise ValidationError(f"{field} '{value}' is too large.")
        return parsed

    def _parse_int(self, value: str | None, *, field: str, default: int, lo: int, hi: int) -> int:
        if not value:
            return default
        try:
            parsed = int(float(value))
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"{field} '{value}' is not a valid integer.") from exc
        if parsed < lo or parsed > hi:
            raise ValidationError(f"{field} must be between {lo} and {hi}.")
        return parsed

    def _parse_date(self, value: str | None):
        if not value:
            return None
        from datetime import date, datetime

        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        raise ValidationError(f"expected_close_date '{value}' is not a recognised date format.")

    def _resolve_stage(
        self,
        raw_value: str | None,
        stage_lookup: dict[str, StageRef],
        industry: LeadIndustry,
        *,
        default: str,
    ) -> StageRef:
        if not raw_value:
            stage = stage_lookup.get(default)
            assert stage is not None, "Default stage missing from pipeline_stages — seed broken."
            return stage
        normalised = raw_value.strip().lower().replace(" / ", " ").replace("/", " ")
        normalised_underscored = normalised.replace(" ", "_")
        # Try code match first, then name match.
        for stage in stage_lookup.values():
            if stage.code.lower() == normalised_underscored:
                return stage
            if stage.name.lower() == raw_value.strip().lower():
                return stage
        raise ValidationError(
            f"Stage '{raw_value}' is not valid for industry '{industry.value}'. "
            f"Use one of: {', '.join(sorted(s.name for s in stage_lookup.values()))}."
        )

    async def _stage_lookup_for_industry(self, industry: LeadIndustry) -> dict[str, StageRef]:
        rows = (
            await self.session.execute(
                select(PipelineStage).where(PipelineStage.industry == industry)
            )
        ).scalars().all()
        # Snapshot to StageRef immediately — this lookup outlives the per-row
        # rollbacks below, and ORM instances do not survive them. See StageRef.
        return {row.code: StageRef(row.code, row.name) for row in rows}

    async def _load_org_or_default_industry(
        self, fallback: LeadIndustry | None
    ) -> Organization | None:
        org_id = current_org(self.session)
        if org_id is None:
            return None
        return (
            await self.session.execute(select(Organization).where(Organization.id == org_id))
        ).scalar_one_or_none()
