from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.orm.interfaces import ORMOption

from app.database.base import Base
from app.schemas.common import PaginationParams


ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    def __init__(self, session: AsyncSession, model: type[ModelType]) -> None:
        self.session = session
        self.model = model

    def _default_filters(self, include_deleted: bool = False) -> list[Any]:
        filters: list[Any] = []
        if hasattr(self.model, "is_deleted") and not include_deleted:
            filters.append(getattr(self.model, "is_deleted").is_(False))
        return filters

    async def get(
        self,
        record_id: UUID,
        *,
        include_deleted: bool = False,
        options: Sequence[ORMOption] | None = None,
    ) -> ModelType | None:
        query = select(self.model).where(*self._default_filters(include_deleted), self.model.id == record_id)
        if options:
            query = query.options(*options)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        pagination: PaginationParams,
        filters: dict[str, Any] | None = None,
        search: str | None = None,
        search_fields: Sequence[str] | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        options: Sequence[ORMOption] | None = None,
        extra_filters: Sequence[Any] | None = None,
    ) -> tuple[list[ModelType], int]:
        query_filters = self._default_filters()
        if filters:
            for field_name, value in filters.items():
                if value is None or not hasattr(self.model, field_name):
                    continue
                column = getattr(self.model, field_name)
                if isinstance(value, (list, tuple, set)):
                    query_filters.append(column.in_(value))
                else:
                    query_filters.append(column == value)

        if search and search_fields:
            pattern = f"%{search.strip()}%"
            search_clauses = []
            for field_name in search_fields:
                if hasattr(self.model, field_name):
                    column: InstrumentedAttribute[Any] = getattr(self.model, field_name)
                    search_clauses.append(cast(column, String).ilike(pattern))
            if search_clauses:
                query_filters.append(or_(*search_clauses))

        # Caller-supplied SQLAlchemy where-clauses (e.g. date ranges the generic
        # equality/IN builder above can't express). Applied to both the row and
        # count queries below, so pagination totals stay correct.
        if extra_filters:
            query_filters.extend(extra_filters)

        query = select(self.model).where(*query_filters)
        count_query = select(func.count()).select_from(self.model).where(*query_filters)

        if options:
            query = query.options(*options)

        order_column = getattr(self.model, sort_by)
        if sort_order == "asc":
            query = query.order_by(order_column.asc())
        else:
            query = query.order_by(order_column.desc())

        query = query.offset(pagination.offset).limit(pagination.page_size)

        total = int((await self.session.execute(count_query)).scalar_one())
        items = list((await self.session.execute(query)).scalars().all())
        return items, total

    async def create(self, payload: dict[str, Any]) -> ModelType:
        instance = self.model(**payload)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def update(self, instance: ModelType, payload: dict[str, Any]) -> ModelType:
        for key, value in payload.items():
            setattr(instance, key, value)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def soft_delete(self, instance: ModelType, deleted_by_id: UUID | None) -> None:
        if hasattr(instance, "is_deleted"):
            instance.is_deleted = True
        if hasattr(instance, "deleted_at"):
            instance.deleted_at = datetime.now(UTC)
        if hasattr(instance, "deleted_by_id"):
            instance.deleted_by_id = deleted_by_id
        await self.session.flush()
