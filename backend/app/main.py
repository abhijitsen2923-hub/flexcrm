from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1.api import api_router
from app.core.cache import cache_client
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.platform_admin import ensure_platform_admin
from app.core.tenancy import register_listeners as register_tenancy_listeners
from app.database.session import db_manager
from app.middleware import RateLimitMiddleware, RequestContextMiddleware
# Import model packages so SQLAlchemy registers mappers for both SharedBase
# and TenantBase before the application starts accepting requests.
import app.models  # noqa: F401
import app.finance.models  # noqa: F401
import app.hr.models  # noqa: F401
import app.real_estate.models  # noqa: F401
import app.customer_portal.models  # noqa: F401
import app.models.custom_role  # noqa: F401


configure_logging()
# Wire the do_orm_execute + before_flush listeners. Idempotent.
register_tenancy_listeners()


@asynccontextmanager
async def lifespan(_: FastAPI):
    db_manager.configure()
    await cache_client.connect()
    await ensure_platform_admin()
    try:
        yield
    finally:
        await cache_client.disconnect()
        await db_manager.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.project_name,
        version="1.0.0",
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/health", tags=["Health"])
    async def health():
        return {"status": "ok"}

    @app.get("/health/db", tags=["Health"])
    async def health_db():
        """Lightweight DB ping. Hit this on a schedule (e.g. every ~4 min) to
        keep the Neon serverless compute warm and avoid cold-start latency on
        the first real query."""
        try:
            async with db_manager.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse(status_code=503, content={"status": "error", "db": "unreachable"})
        return {"status": "ok", "db": "ok"}

    return app


app = create_app()
