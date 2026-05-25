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
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.core.currencies import DEFAULT_CURRENCY, allowed_currencies_for_org
from app.core.exceptions import AppException, ValidationError
from app.core.tenancy import current_org
from app.database.enums import LeadIndustry, UserRole
from app.database.pipeline_seed import initial_stage_code
from app.models.organization import Organization
from app.models.pipeline_stage import PipelineStage
from app.repositories.leads import LeadRepository
from app.schemas.lead import LeadCreate
from app.schemas.stage_transition import StageTransitionCreate
from app.services.base import ServiceBase
from app.services.leads import LeadService
from app.services.stage_transitions import StageTransitionService


# Header aliases — we accept either the exact column name or a friendlier
# variant. Keys are the canonical names used by the service.
HEADER_ALIASES: dict[str, set[str]] = {
    "contact_name": {"contact_name", "name", "lead_name", "contact"},
    "title": {"title", "subject", "lead_title"},
    "contact_email": {"contact_email", "email"},
    "contact_phone": {"contact_phone", "phone", "mobile"},
    "company_name": {"company_name", "company", "organization", "org", "company / organization"},
    "stage": {"stage", "stage_code", "lead_stage", "status"},
    "source": {"source", "lead_source"},
    "interest": {"interest", "course", "destination", "course_destination"},
    "value": {"value", "amount", "deal_value"},
    "currency": {"currency", "currency_code"},
    "probability": {"probability", "prob", "probability (%)"},
    "expected_close_date": {"expected_close_date", "close_date", "expected_close", "expected close"},
}


@dataclass
class ImportRowError:
    row: int
    error: str


@dataclass
class ImportSummary:
    created: int = 0
    promoted: int = 0
    errors: list[ImportRowError] = field(default_factory=list)


class LeadImportService(ServiceBase):
    """CSV → leads. Reuses `LeadService` + `StageTransitionService` for parity
    with manual creation."""

    def __init__(self, session):
        super().__init__(session)
        self.lead_service = LeadService(session)
        self.transition_service = StageTransitionService(session)
        self.lead_repository = LeadRepository(session)

    async def import_csv(
        self,
        file_bytes: bytes,
        *,
        actor_id: UUID,
        actor_role: UserRole,
        actor_business_type: LeadIndustry | None,
    ) -> ImportSummary:
        try:
            text = file_bytes.decode("utf-8-sig")  # tolerate BOM from Excel exports
        except UnicodeDecodeError as exc:
            raise ValidationError("CSV must be UTF-8 encoded.") from exc

        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None:
            raise ValidationError("CSV is empty or has no header row.")

        # Build a canonical-name → actual-header map from the CSV's columns.
        header_map = self._build_header_map(reader.fieldnames)
        if "contact_name" not in header_map:
            raise ValidationError(
                "CSV must include a `contact_name` column (aliases: name, lead_name, contact)."
            )

        # Pre-load the org so we can validate currency + stages per row.
        org = await self._load_org_or_default_industry(actor_business_type)
        industry = org.business_type if org else actor_business_type
        if industry is None:
            raise ValidationError(
                "Cannot determine the import industry — your account has no business_type set."
            )

        allowed_currencies = allowed_currencies_for_org(org) if org else [DEFAULT_CURRENCY]
        stage_lookup = await self._stage_lookup_for_industry(industry)
        initial_code = initial_stage_code(industry.value)

        summary = ImportSummary()

        # CSV row numbering starts at 2 (header is row 1) so the user can
        # cross-reference with their spreadsheet.
        for offset, raw in enumerate(reader, start=2):
            row = {canonical: self._read_field(raw, header_map.get(canonical)) for canonical in HEADER_ALIASES}
            try:
                created_lead_id, was_promoted = await self._import_row(
                    row,
                    actor_id=actor_id,
                    actor_role=actor_role,
                    industry=industry,
                    initial_code=initial_code,
                    allowed_currencies=allowed_currencies,
                    stage_lookup=stage_lookup,
                )
            except ValidationError as exc:
                summary.errors.append(ImportRowError(row=offset, error=exc.detail))
                # Roll back any partial state from this row so the next row
                # starts clean.
                await self.session.rollback()
                continue
            except AppException as exc:
                summary.errors.append(ImportRowError(row=offset, error=exc.detail))
                await self.session.rollback()
                continue
            except Exception as exc:  # noqa: BLE001 — surface unknown errors per-row, don't kill the batch
                summary.errors.append(ImportRowError(row=offset, error=f"Unexpected error: {exc}"))
                await self.session.rollback()
                continue

            summary.created += 1
            if was_promoted:
                summary.promoted += 1

        return summary

    # --- per-row work ------------------------------------------------------

    async def _import_row(
        self,
        row: dict[str, str | None],
        *,
        actor_id: UUID,
        actor_role: UserRole,
        industry: LeadIndustry,
        initial_code: str,
        allowed_currencies: list[str],
        stage_lookup: dict[str, PipelineStage],
    ) -> tuple[UUID, bool]:
        contact_name = (row.get("contact_name") or "").strip()
        if not contact_name:
            raise ValidationError("contact_name is required.")

        title = (row.get("title") or "").strip() or contact_name

        currency = (row.get("currency") or DEFAULT_CURRENCY).strip().upper() or DEFAULT_CURRENCY
        if currency not in allowed_currencies:
            raise ValidationError(
                f"Currency '{currency}' is not enabled for this org. Allowed: {', '.join(allowed_currencies)}."
            )

        value = self._parse_decimal(row.get("value"), field="value", default=Decimal("0"))
        probability = self._parse_int(row.get("probability"), field="probability", default=0, lo=0, hi=100)

        target_stage = self._resolve_stage(row.get("stage"), stage_lookup, industry, default=initial_code)

        payload = LeadCreate(
            industry=industry,
            title=title,
            contact_name=contact_name,
            contact_email=row.get("contact_email") or None,
            contact_phone=row.get("contact_phone") or None,
            company_name=row.get("company_name") or None,
            value=value,
            currency=currency,
            probability=probability,
            source=row.get("source") or None,
            interest=row.get("interest") or None,
            expected_close_date=self._parse_date(row.get("expected_close_date")),
        )

        lead = await self.lead_service.create_lead(
            payload, actor_id=actor_id, actor_business_type=industry
        )

        was_promoted = False
        if target_stage.code != initial_code:
            # Move the lead to the requested stage via the regular transition
            # service so all side effects (comment log, realtime broadcast,
            # auto-promotion on Sold) fire identically to manual moves.
            await self.transition_service.create_transition(
                lead.id,
                StageTransitionCreate(
                    to_stage_code=target_stage.code,
                    comment=f"Imported from CSV upload — initial stage set to {target_stage.name}.",
                ),
                actor_id=actor_id,
                actor_role=actor_role,
            )
            if target_stage.code == "sold":
                was_promoted = True

        return lead.id, was_promoted

    # --- helpers -----------------------------------------------------------

    def _build_header_map(self, fieldnames: list[str]) -> dict[str, str]:
        """Map canonical names to the actual headers present in the CSV.

        Lowercases + strips both sides. The first matching alias wins.
        """
        normalised = {(h or "").strip().lower(): h for h in fieldnames}
        out: dict[str, str] = {}
        for canonical, aliases in HEADER_ALIASES.items():
            for alias in aliases:
                if alias in normalised:
                    out[canonical] = normalised[alias]
                    break
        return out

    def _read_field(self, raw: dict[str, Any], header: str | None) -> str | None:
        if header is None:
            return None
        value = raw.get(header)
        if value is None:
            return None
        text = str(value).strip()
        return text if text else None

    def _parse_decimal(self, value: str | None, *, field: str, default: Decimal) -> Decimal:
        if not value:
            return default
        try:
            return Decimal(value.replace(",", ""))
        except (InvalidOperation, ValueError) as exc:
            raise ValidationError(f"{field} '{value}' is not a valid number.") from exc

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
        stage_lookup: dict[str, PipelineStage],
        industry: LeadIndustry,
        *,
        default: str,
    ) -> PipelineStage:
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

    async def _stage_lookup_for_industry(self, industry: LeadIndustry) -> dict[str, PipelineStage]:
        rows = (
            await self.session.execute(
                select(PipelineStage).where(PipelineStage.industry == industry)
            )
        ).scalars().all()
        return {row.code: row for row in rows}

    async def _load_org_or_default_industry(
        self, fallback: LeadIndustry | None
    ) -> Organization | None:
        org_id = current_org(self.session)
        if org_id is None:
            return None
        return (
            await self.session.execute(select(Organization).where(Organization.id == org_id))
        ).scalar_one_or_none()
