from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import selectinload

from app.core.tenancy import current_org
from app.models.lead import Lead
from app.models.user import User
from app.repositories.base import BaseRepository


# First lead_number issued matches the spec's example "89002" — close enough to
# give freshly seeded databases lead IDs that look like the v2 examples.
LEAD_NUMBER_START = 89000
# Advisory-lock namespace for lead_number allocation (any constant int4 unique to this use).
_LEAD_NUMBER_LOCK_NAMESPACE = 72001


class LeadRepository(BaseRepository[Lead]):
    def __init__(self, session):
        super().__init__(session, Lead)

    @property
    def default_options(self):
        return [selectinload(Lead.customer), selectinload(Lead.assigned_to), selectinload(Lead.partner)]

    async def find_duplicates(
        self,
        email: str | None,
        phone_digits: str | None,
        limit: int = 5,
        owner_id=None,
    ) -> list[Lead]:
        """Active leads whose (lowercased) email or digits-only phone matches.

        Per-tenant is automatic: this session's schema routing scopes the query
        to the caller's tenant schema. When `owner_id` is set the match is further
        restricted to that owner's leads (front-line reps must not discover other
        reps' leads by probing contacts). Returns [] when both inputs are blank.
        """
        clauses = []
        if email:
            clauses.append(func.lower(Lead.contact_email) == email)
        if phone_digits:
            clauses.append(
                func.regexp_replace(Lead.contact_phone, r"[^0-9]", "", "g") == phone_digits
            )
        if not clauses:
            return []
        where = [Lead.is_deleted.is_(False), or_(*clauses)]
        if owner_id is not None:
            where.append(Lead.assigned_to_id == owner_id)
        rows = await self.session.execute(
            select(Lead).where(*where).order_by(Lead.created_at.desc()).limit(limit)
        )
        return list(rows.scalars().all())

    async def duplicate_numbers(self, emails: set[str], phone_digits: set[str]) -> dict[str, list[int]]:
        """For a CSV import: numbers of active leads whose lowercased email / digits-only phone is in the
        given sets, keyed "e:<email>" / "p:<digits>", newest first — ONE query per 500 keys instead of a
        full-table duplicate scan per row. Same matching as `find_duplicates`."""
        email_expr = func.lower(Lead.contact_email)
        phone_expr = func.regexp_replace(Lead.contact_phone, r"[^0-9]", "", "g")
        email_list, phone_list = sorted(emails), sorted(phone_digits)
        out: dict[str, list[int]] = {}

        def _add(key: str, number: int) -> None:
            numbers = out.setdefault(key, [])
            if number not in numbers:
                numbers.append(number)

        batch = 500
        for start in range(0, max(len(email_list), len(phone_list)), batch):
            e_chunk, p_chunk = email_list[start:start + batch], phone_list[start:start + batch]
            clauses = []
            if e_chunk:
                clauses.append(email_expr.in_(e_chunk))
            if p_chunk:
                clauses.append(phone_expr.in_(p_chunk))
            rows = await self.session.execute(
                select(Lead.lead_number, email_expr, phone_expr)
                .where(Lead.is_deleted.is_(False), or_(*clauses))
                .order_by(Lead.lead_number.desc())
            )
            for number, email, phone in rows:
                if email and email in emails:
                    _add(f"e:{email}", number)
                if phone and phone in phone_digits:
                    _add(f"p:{phone}", number)
        for numbers in out.values():
            numbers.sort(reverse=True)
        return out

    async def duplicate_contact_keys(self) -> tuple[set[str], set[str]]:
        """Normalized email + digits-only phone values shared by >1 active lead.

        Two tenant-scoped aggregate queries (independent of page size) used to
        flag which leads in a list page are duplicates. Blank/empty keys are
        excluded so leads without an email or phone are never flagged.
        """
        email_expr = func.lower(Lead.contact_email)
        email_rows = await self.session.execute(
            select(email_expr)
            .where(Lead.is_deleted.is_(False), Lead.contact_email.is_not(None))
            .group_by(email_expr)
            .having(func.count() > 1)
        )
        phone_expr = func.regexp_replace(Lead.contact_phone, r"[^0-9]", "", "g")
        phone_rows = await self.session.execute(
            select(phone_expr)
            .where(
                Lead.is_deleted.is_(False),
                Lead.contact_phone.is_not(None),
                phone_expr != "",
            )
            .group_by(phone_expr)
            .having(func.count() > 1)
        )
        return (
            {r for (r,) in email_rows if r},
            {r for (r,) in phone_rows if r},
        )

    async def duplicate_assignment_map(self, phone_keys: set[str]) -> dict[str, list[tuple]]:
        """{phone_key: [(lead_id, "First Last"), …]} for ASSIGNED active leads whose
        digits-only phone is one of `phone_keys`, earliest-assigned first. Powers the
        "fresh vs already assigned to <owner>" duplicate label; the joined public.users
        row is org-filtered (users are cross-tenant)."""
        if not phone_keys:
            return {}
        org_id = current_org(self.session)
        phone_expr = func.regexp_replace(Lead.contact_phone, r"[^0-9]", "", "g")
        rows = await self.session.execute(
            select(phone_expr.label("k"), Lead.id, User.first_name, User.last_name)
            .join(User, User.id == Lead.assigned_to_id)
            .where(
                Lead.is_deleted.is_(False),
                Lead.assigned_to_id.is_not(None),
                User.organization_id == org_id,
                phone_expr.in_(phone_keys),
            )
            .order_by(Lead.created_at.asc())
        )
        out: dict[str, list[tuple]] = {}
        for key, lead_id, first_name, last_name in rows:
            name = f"{(first_name or '').strip()} {(last_name or '').strip()}".strip()
            out.setdefault(key, []).append((lead_id, name))
        return out

    async def distinct_campaigns(self, owner_id=None) -> list[str]:
        """Distinct non-empty campaign values across the tenant's active leads.

        Powers the list's Campaign filter dropdown so imported/custom campaigns —
        not just the app's predefined labels — are selectable. Tenant-scoped by
        the session's schema routing. When `owner_id` is set (front-line reps),
        restrict to that owner's leads — the same anti-poaching scope the list
        and duplicate-check paths enforce, so a rep can't discover campaign names
        used only on other reps' leads.
        """
        where = [
            Lead.is_deleted.is_(False),
            Lead.campaign.is_not(None),
            Lead.campaign != "",
        ]
        if owner_id is not None:
            where.append(Lead.assigned_to_id == owner_id)
        rows = await self.session.execute(
            select(Lead.campaign).where(*where).distinct().order_by(Lead.campaign)
        )
        return [c for (c,) in rows if c]

    async def next_lead_number(self) -> int:
        """MAX+1 within the tenant. On Postgres a transaction-scoped advisory lock per tenant schema serialises
        concurrent creators (New Lead, CSV import, sheet/Meta ingest, portals), so two can't read the same MAX
        and collide on uq_leads_lead_number. It's released automatically at commit/rollback (every caller
        commits within milliseconds); other tenants never wait on it."""
        bind = self.session.bind
        if bind is not None and bind.dialect.name == "postgresql":
            await self.session.execute(
                text("SELECT pg_advisory_xact_lock(:namespace, hashtext(:tenant))"),
                {"namespace": _LEAD_NUMBER_LOCK_NAMESPACE, "tenant": self.session.info.get("schema_name") or "public"},
            )
        current_max = (
            await self.session.execute(select(func.max(Lead.lead_number)))
        ).scalar_one()
        return (current_max or LEAD_NUMBER_START) + 1
