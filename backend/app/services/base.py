from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_client
from app.core.exceptions import ConflictError


class ServiceBase:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def commit(self) -> None:
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("A database constraint was violated.") from exc
        except Exception:
            await self.session.rollback()
            raise

    async def invalidate_reporting_cache(self) -> None:
        await cache_client.delete_pattern("dashboard:")
        await cache_client.delete_pattern("analytics:")
