from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared (public schema) models: organizations, users, refresh_tokens, pipeline_stages."""


class TenantBase(DeclarativeBase):
    """Per-tenant schema models. The literal schema name 'tenant' in each
    model's __table_args__ is replaced at query time via SQLAlchemy's
    schema_translate_map execution option set on the connection.

    The metadata carries a default schema of 'tenant' so that unqualified
    ForeignKey strings between tenant tables (e.g. ForeignKey("customers.id"))
    resolve to the schema-qualified table key 'tenant.customers'. Without this,
    mapper configuration fails with NoReferencedTableError the first time a
    tenant model is queried, because the table is registered as 'tenant.<name>'
    while the FK looks up the bare '<name>'."""

    metadata = MetaData(schema="tenant")
