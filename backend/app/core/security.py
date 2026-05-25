from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def generate_token_id() -> str:
    return uuid4().hex


def _build_token(
    *,
    subject: str,
    token_type: str,
    secret: str,
    expires_delta: timedelta,
    extra: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "jti": generate_token_id(),
    }
    if extra:
        payload.update(extra)

    settings = get_settings()
    return jwt.encode(payload, secret, algorithm=settings.jwt_algorithm)


def create_access_token(subject: str, *, role: str, organization_id: str | None = None) -> tuple[str, datetime]:
    settings = get_settings()
    expires_delta = timedelta(minutes=settings.access_token_expires_minutes)
    expires_at = datetime.now(UTC) + expires_delta
    extra: dict[str, Any] = {"role": role}
    # Embed the org id so request handlers can scope queries without an extra
    # DB lookup (the User row already carries it, but the JWT path is hot).
    if organization_id is not None:
        extra["org"] = organization_id
    token = _build_token(
        subject=subject,
        token_type="access",
        secret=settings.jwt_secret_key,
        expires_delta=expires_delta,
        extra=extra,
    )
    return token, expires_at


def create_refresh_token(subject: str) -> tuple[str, datetime]:
    settings = get_settings()
    expires_delta = timedelta(days=settings.refresh_token_expires_days)
    expires_at = datetime.now(UTC) + expires_delta
    token = _build_token(
        subject=subject,
        token_type="refresh",
        secret=settings.jwt_refresh_secret_key,
        expires_delta=expires_delta,
    )
    return token, expires_at


def decode_token(token: str, *, refresh: bool = False) -> dict[str, Any]:
    settings = get_settings()
    secret = settings.jwt_refresh_secret_key if refresh else settings.jwt_secret_key

    try:
        payload = jwt.decode(token, secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise AuthenticationError("Invalid or expired token") from exc

    return payload


def get_bearer_token(credentials: HTTPAuthorizationCredentials | None) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError("Missing bearer token")
    return credentials.credentials
