from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.cache import cache_client
from app.core.config import get_settings
from app.core.logging import request_id_context


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        path = request.url.path
        # Inbound webhooks (Meta, 99acres, …) are authenticated by their own token/signature and
        # must not be IP-rate-limited: behind Cloud Run every caller shares one client IP (uvicorn
        # runs without --proxy-headers), so a shared limiter would throttle all tenants' leads at
        # once. They ACK-then-process, so volume is bounded server-side anyway.
        if path in {"/health", "/docs", "/openapi.json", "/redoc"} or path.startswith(
            f"{settings.api_v1_prefix}/webhooks/"
        ):
            return await call_next(request)

        client_host = request.client.host if request.client else "unknown"
        key = f"ratelimit:{client_host}:{request.url.path}"
        count = await cache_client.increment(key, ttl_seconds=60)
        if count > settings.rate_limit_per_minute:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": {
                        "code": "rate_limit_exceeded",
                        "detail": "Rate limit exceeded. Please retry later.",
                    },
                    "request_id": request_id_context.get(),
                    "path": request.url.path,
                },
            )

        return await call_next(request)
