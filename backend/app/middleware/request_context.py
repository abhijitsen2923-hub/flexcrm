import time
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.logging import get_logger, request_id_context


logger = get_logger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", uuid4().hex)
        request.state.request_id = request_id
        token = request_id_context.set(request_id)
        started_at = time.perf_counter()

        try:
            response = await call_next(request)
        finally:
            duration_ms = (time.perf_counter() - started_at) * 1000
            logger.info(
                "%s %s completed in %.2fms",
                request.method,
                request.url.path,
                duration_ms,
            )
            request_id_context.reset(token)

        response.headers["X-Request-ID"] = request_id
        return response
