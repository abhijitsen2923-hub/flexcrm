from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.refresh_token import RefreshToken
from app.repositories.base import BaseRepository


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    """Refresh tokens rotate: each renewal revokes the token it used (`revoked_at`) and issues a new one. A token
    ended on purpose (sign-out, user removed) also gets `expires_at` = now, so it can never renew again — not even
    inside the reuse grace period (see get_recently_rotated)."""

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

    async def get_recently_rotated(self, token_id: str, *, grace_seconds: int) -> RefreshToken | None:
        """A token replaced by a renewal within the last `grace_seconds` and not ended on purpose."""
        if grace_seconds <= 0:
            return None
        now = datetime.now(UTC)
        query = select(RefreshToken).where(
            RefreshToken.token_id == token_id,
            RefreshToken.revoked_at.is_not(None),
            RefreshToken.revoked_at >= now - timedelta(seconds=grace_seconds),
            RefreshToken.expires_at > now,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_token_id(self, token_id: str) -> RefreshToken | None:
        result = await self.session.execute(select(RefreshToken).where(RefreshToken.token_id == token_id))
        return result.scalar_one_or_none()

    async def revoke(self, token: RefreshToken) -> None:
        """Rotation: this token was just renewed (it may still renew inside the grace period)."""
        token.revoked_at = datetime.now(UTC)
        await self.session.flush()

    async def end(self, token: RefreshToken) -> None:
        """Ended on purpose (sign-out): never renews again."""
        now = datetime.now(UTC)
        token.revoked_at = token.revoked_at or now
        token.expires_at = now
        await self.session.flush()

    async def end_recent_rotations(self, user_id, *, grace_seconds: int) -> None:
        """At sign-out: the user's tokens still inside the grace period end too, so the one renewed just before
        signing out can't bring the session back."""
        now = datetime.now(UTC)
        query = select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_not(None),
            RefreshToken.revoked_at >= now - timedelta(seconds=max(grace_seconds, 0)),
            RefreshToken.expires_at > now,
        )
        for token in (await self.session.execute(query)).scalars().all():
            token.expires_at = now
        await self.session.flush()

    async def revoke_for_user(self, user_id) -> None:
        """Every token of the user ends now (user removed) — the grace period included."""
        now = datetime.now(UTC)
        query = select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.expires_at > now,
        )
        result = await self.session.execute(query)
        for token in result.scalars().all():
            token.revoked_at = token.revoked_at or now
            token.expires_at = now
        await self.session.flush()
