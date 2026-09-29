from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.services.bulk_scope import invalidate_reporting_cache_now, pending_side_effects


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
        bulk = pending_side_effects()
        if bulk is not None:
            bulk.invalidate_cache = True  # wiped once when the bulk write (CSV import) ends
            return
        await invalidate_reporting_cache_now()
