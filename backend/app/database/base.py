from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared (public schema) models: organizations, users, refresh_tokens, pipeline_stages."""


class TenantBase(DeclarativeBase):
    """Per-tenant schema models. The literal schema name 'tenant' in each
    model's __table_args__ is replaced at query time via SQLAlchemy's
    schema_translate_map execution option set on the connection."""
