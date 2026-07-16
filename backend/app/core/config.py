from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


# Default placeholder values. Production deploys must override these via env
# vars; otherwise the app refuses to start (see `_reject_insecure_production`).
_DEFAULT_JWT_ACCESS = "change-me-access-secret"
_DEFAULT_JWT_REFRESH = "change-me-refresh-secret"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    project_name: str = "FlexCRM API"
    environment: Literal["local", "test", "staging", "production"] = "local"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/crm"
    # If SYNC_DATABASE_URL is not set, it is derived from DATABASE_URL by
    # replacing the asyncpg driver prefix. This covers Cloud Run deployments
    # where only DATABASE_URL is configured (Alembic needs a sync psycopg2 URL).
    sync_database_url: str | None = None
    sqlalchemy_echo: bool = False

    jwt_secret_key: str = Field(default=_DEFAULT_JWT_ACCESS, min_length=16)
    jwt_refresh_secret_key: str = Field(default=_DEFAULT_JWT_REFRESH, min_length=16)
    jwt_algorithm: str = "HS256"
    access_token_expires_minutes: int = 15
    refresh_token_expires_days: int = 7

    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 300
    rate_limit_per_minute: int = 120

    # `NoDecode` disables pydantic-settings' built-in JSON decoder for this
    # field so the `parse_cors_origins` validator below can accept a plain
    # comma-separated string from the environment.
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://flexcrm.abhijitsen2923.workers.dev",
    ]
    docs_enabled: bool = True

    # When true, 500 responses include the exception type/message to aid
    # debugging. Default true during stabilization; set EXPOSE_ERROR_DETAIL=false
    # in the deployment env before go-live so internals aren't leaked to clients.
    expose_error_detail: bool = True

    # --- Platform admin bootstrap (optional) ---
    # Set these once to have the app create/promote a platform admin on startup.
    # Idempotent — safe to leave set after the first run.
    platform_admin_email: str | None = None
    platform_admin_password: str | None = None

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_sender: str = "noreply@flexcrm.local"
    smtp_use_tls: bool = True

    # --- Email delivery (Resend transactional API over HTTPS) ---
    # When `resend_api_key` is unset, every email is a logged no-op (so dev and
    # not-yet-configured deploys stay fully functional). `email_from` must be a
    # verified Resend sender ("Name <addr@your-domain>"). `app_base_url` is the
    # frontend origin used to build "open in FlexCRM" links inside emails.
    resend_api_key: str | None = None
    email_from: str = "FlexCRM <onboarding@resend.dev>"
    app_base_url: str = "https://flexcrm.example.com"

    # --- Object storage (S3-compatible: Backblaze B2 / Cloudflare R2 / AWS S3) ---
    # When these are unset, file upload/download endpoints return a clean 503
    # ("File storage is not configured") instead of 500ing — so local/dev and
    # not-yet-provisioned deploys stay functional for everything else.
    s3_endpoint_url: str | None = None
    s3_region: str | None = None
    s3_bucket: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_presign_ttl_seconds: int = 3600

    # Shared secret for machine-triggered cron endpoints (e.g. the Cloudflare
    # Worker that fires registration reminders). When unset, those endpoints
    # reject every call (403) — so they're inert until deliberately enabled.
    cron_secret: str | None = None

    websocket_ping_interval_seconds: int = 20
    websocket_event_buffer_size: int = 200

    archival_retention_days: int = 90

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def _derive_sync_url(self) -> "Settings":
        """Derive sync_database_url from database_url when not explicitly set."""
        if self.sync_database_url is None:
            self.sync_database_url = self.database_url.replace(
                "postgresql+asyncpg://", "postgresql://"
            )
        return self

    @model_validator(mode="after")
    def _reject_insecure_production(self) -> "Settings":
        """Fail fast if a deployed environment is missing critical config.

        `staging` and `production` MUST set real JWT secrets and a non-wildcard
        CORS list. We catch the misconfig here instead of letting the app boot
        with placeholder values and silently issue tokens an attacker can mint.
        `local` and `test` skip the check so dev / pytest stay frictionless.
        """
        if self.environment not in {"staging", "production"}:
            return self

        problems: list[str] = []
        if self.jwt_secret_key == _DEFAULT_JWT_ACCESS:
            problems.append("JWT_SECRET_KEY is the placeholder; set a real 32+ byte secret")
        if self.jwt_refresh_secret_key == _DEFAULT_JWT_REFRESH:
            problems.append("JWT_REFRESH_SECRET_KEY is the placeholder; set a real 32+ byte secret")
        if not self.cors_origins or "*" in self.cors_origins:
            problems.append("CORS_ORIGINS must list explicit origins (no wildcard)")

        if problems:
            raise ValueError(
                f"Refusing to start in {self.environment} with insecure config:\n  - "
                + "\n  - ".join(problems)
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
