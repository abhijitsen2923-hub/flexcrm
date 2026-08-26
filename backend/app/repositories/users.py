from uuid import UUID

from sqlalchemy import select

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session):
        super().__init__(session, User)

    async def get_in_org(self, user_id: UUID, organization_id: UUID | None) -> User | None:
        """Fetch a user only if they belong to `organization_id`.

        `users` is a shared/public table (never schema-translated), so the base
        `get()` resolves a user in ANY org. Every assignee/owner reference must
        scope by org through this method — otherwise a caller can assign a lead
        or task to a user in another tenant by supplying their UUID (cross-tenant
        IDOR). Returns None (→ 404 at the service layer) when the user is absent,
        deleted, or in a different org.
        """
        query = select(User).where(User.id == user_id, User.is_deleted.is_(False))
        if organization_id is not None:
            query = query.where(User.organization_id == organization_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        # Case-insensitive: emails are stored lowercased (see NormalizedEmail +
        # the lower(email) unique index), and we normalize here so any caller
        # passing mixed case still matches.
        query = select(User).where(
            User.email == email.strip().lower(), User.is_deleted.is_(False)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def has_active_users(self) -> bool:
        query = select(User.id).where(User.is_deleted.is_(False)).limit(1)
        result = await self.session.execute(query)
        return result.scalar_one_or_none() is not None
