from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.models.lead import Lead
from app.repositories.base import BaseRepository


# First lead_number issued matches the spec's example "89002" — close enough to
# give freshly seeded databases lead IDs that look like the v2 examples.
LEAD_NUMBER_START = 89000


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

    async def next_lead_number(self) -> int:
        # The DB has a unique constraint on lead_number; this MAX+1 lookup is
        # safe for a single-writer dev/demo workload. Replace with a Postgres
        # sequence if/when concurrent writers become a concern.
        current_max = (
            await self.session.execute(select(func.max(Lead.lead_number)))
        ).scalar_one()
        return (current_max or LEAD_NUMBER_START) + 1
