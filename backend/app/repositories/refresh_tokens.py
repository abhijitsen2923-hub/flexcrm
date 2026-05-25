from datetime import UTC, datetime

from sqlalchemy import select

from app.models.refresh_token import RefreshToken
from app.repositories.base import BaseRepository


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    def __init__(self, session):
        super().__init__(session, RefreshToken)

    async def get_active(self, token_id: str) -> RefreshToken | None:
        query = select(RefreshToken).where(
            RefreshToken.token_id == token_id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > datetime.now(UTC),
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def revoke(self, token: RefreshToken) -> None:
        token.revoked_at = datetime.now(UTC)
        await self.session.flush()

    async def revoke_for_user(self, user_id) -> None:
        query = select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
        result = await self.session.execute(query)
        for token in result.scalars().all():
            token.revoked_at = datetime.now(UTC)
        await self.session.flush()
