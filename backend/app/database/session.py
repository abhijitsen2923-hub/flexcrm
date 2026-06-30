from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


class DatabaseSessionManager:
    def __init__(self) -> None:
        self._database_url: str | None = None
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    def configure(self, database_url: str | None = None) -> None:
        settings = get_settings()
        resolved_url = database_url or settings.database_url
        if self._database_url == resolved_url and self._engine and self._session_factory:
            return

        self._database_url = resolved_url
        self._engine = create_async_engine(
            resolved_url,
            echo=settings.sqlalchemy_echo,
            future=True,
            pool_pre_ping=True,
            # Explicit, bounded pool: 20 conns/instance gives headroom for ~30
            # concurrent users. pool_recycle drops connections Neon has idle-closed
            # before we reuse them (works with pre_ping). Keep DATABASE_URL on
            # Neon's pooled (-pooler) endpoint so instances share real connections.
            pool_size=10,
            max_overflow=10,
            pool_timeout=20,
            pool_recycle=300,
        )
        self._session_factory = async_sessionmaker(
            bind=self._engine,
            autoflush=False,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    @property
    def engine(self) -> AsyncEngine:
        if self._engine is None:
            self.configure()
        assert self._engine is not None
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        if self._session_factory is None:
            self.configure()
        assert self._session_factory is not None
        return self._session_factory

    async def dispose(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            self._database_url = None


db_manager = DatabaseSessionManager()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with db_manager.session_factory() as session:
        yield session
