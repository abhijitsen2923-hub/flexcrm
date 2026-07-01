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
        return [selectinload(Lead.customer), selectinload(Lead.assigned_to)]

    async def find_duplicates(
        self, email: str | None, phone_digits: str | None, limit: int = 5
    ) -> list[Lead]:
        """Active leads whose (lowercased) email or digits-only phone matches.

        Per-tenant is automatic: this session's schema routing scopes the query
        to the caller's tenant schema. Returns [] when both inputs are blank.
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
        rows = await self.session.execute(
            select(Lead)
            .where(Lead.is_deleted.is_(False), or_(*clauses))
            .order_by(Lead.created_at.desc())
            .limit(limit)
        )
        return list(rows.scalars().all())

    async def next_lead_number(self) -> int:
        # The DB has a unique constraint on lead_number; this MAX+1 lookup is
        # safe for a single-writer dev/demo workload. Replace with a Postgres
        # sequence if/when concurrent writers become a concern.
        current_max = (
            await self.session.execute(select(func.max(Lead.lead_number)))
        ).scalar_one()
        return (current_max or LEAD_NUMBER_START) + 1
