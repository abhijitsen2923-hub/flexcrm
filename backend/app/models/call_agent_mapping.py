"""Manual caller → FlexCRM-user mapping for Callyzer call attribution (per-tenant).

When a device number (emp_number) doesn't auto-match a user by phone, a manager pins it
here. The sync prefers these overrides over the phone auto-match, and existing calls are
re-attributed the moment a mapping is created — so employee call-performance stays correct.
Matched on the normalised last-10 digits (emp_key), like the lead-side matcher.
"""
from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import TenantBase
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class CallAgentMapping(TenantBase, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "call_agent_mappings"
    __table_args__ = (
        UniqueConstraint("provider", "emp_key", name="uq_call_agent_mappings_provider_emp_key"),
        {"schema": "tenant"},
    )

    provider: Mapped[str] = mapped_column(String(20), nullable=False, default="callyzer")
    # Normalised last-10 digits of the device number — the match key.
    emp_key: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    emp_number: Mapped[str | None] = mapped_column(String(32), nullable=True)  # raw, for display
    emp_name: Mapped[str | None] = mapped_column(String(160), nullable=True)   # last-seen Callyzer name
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("public.users.id", ondelete="CASCADE"), nullable=False
    )
    created_by_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("public.users.id", ondelete="SET NULL"), nullable=True
    )
