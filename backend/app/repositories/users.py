from sqlalchemy import select

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session):
        super().__init__(session, User)

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
