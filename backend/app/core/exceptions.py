from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import get_logger, request_id_context


logger = get_logger(__name__)


class AppException(Exception):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "application_error"

    def __init__(self, detail: str, *, extra: Mapping[str, Any] | None = None) -> None:
        self.detail = detail
        self.extra = dict(extra or {})
        super().__init__(detail)


class NotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ConflictError(AppException):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class AuthenticationError(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "authentication_error"


class AuthorizationError(AppException):
    status_code = status.HTTP_403_FORBIDDEN
    code = "authorization_error"


class ServiceUnavailableError(AppException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "service_unavailable"


class ValidationError(AppException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "validation_error"


def _build_error_payload(detail: Any, code: str, request: Request, extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "detail": detail,
            "extra": dict(extra or {}),
        },
        "request_id": request_id_context.get(),
        "path": request.url.path,
    }


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    logger.warning("Application error raised: %s", exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=_build_error_payload(exc.detail, exc.code, request, exc.extra),
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if exc.detail else "HTTP error"
    return JSONResponse(
        status_code=exc.status_code,
        content=_build_error_payload(detail, "http_error", request),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Pydantic 2's `exc.errors()` can embed raw Decimal/UUID/etc. inside ctx
    # for Decimal/UUID-typed fields. Run through `jsonable_encoder` to coerce
    # them into JSON-safe primitives before handing off to Starlette's JSON.
    errors = jsonable_encoder(exc.errors())
    logger.info("Validation failed for %s: %s", request.url.path, errors)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_build_error_payload(errors, "request_validation_error", request),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_build_error_payload(
            f"Internal server error: {type(exc).__name__}: {exc}",
            "internal_server_error",
            request,
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
