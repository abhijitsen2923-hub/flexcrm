from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, exists, select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models import Activity, Customer, Deal, Lead, Notification, Task, User


logger = get_logger(__name__)


@dataclass
class ArchivalReport:
    cutoff: datetime
    deleted: dict[str, int] = field(default_factory=dict)
    skipped_customers: int = 0
    orgs: int = 0


def retention_cutoff(retention_days: int | None = None) -> datetime | None:
    """UTC instant before which soft-deleted rows may be hard-deleted.

    Returns None when archival is disabled (retention <= 0).
    """
    settings = get_settings()
    days = retention_days if retention_days is not None else settings.archival_retention_days
    if days <= 0:
        return None
    return datetime.now(UTC) - timedelta(days=days)


class ArchivalService:
    """Hard-delete rows soft-deleted for longer than the retention window.

    The work is split in two because the data lives in two places under
    schema-per-tenant:

    * :meth:`purge_tenant_scope` — the per-tenant tables. Must run once per org,
      with the session already routed to that org's schema via
      ``set_tenant_schema``. Every model it touches declares
      ``{"schema": "tenant"}``.
    * :meth:`purge_public_users` — ``users`` lives in ``public`` and is shared by
      every tenant, so it is purged exactly ONCE for the whole platform, with
      routing cleared. Running it inside the org loop would re-scan (and
      re-report) the same rows for every org.

    The org loop itself is ``dispatch_archival`` in ``app/jobs/archive.py``.

    Deletion order respects RESTRICT FKs:
    Notification, Activity, Task → Lead, Deal → Customer → User.
    Customers with any live (non-soft-deleted) Lead or Deal referencing them are
    skipped to avoid breaking RESTRICT.
    """

    _TENANT_MODELS = (Notification, Activity, Task, Lead, Deal)

    async def purge_tenant_scope(self, session, cutoff: datetime) -> tuple[dict[str, int], int]:
        """Purge the current tenant schema. Returns (deleted-per-table, skipped customers).

        Does not commit — the caller owns the transaction so one org's failure
        can be rolled back without affecting the others.
        """
        deleted: dict[str, int] = {}

        for model in self._TENANT_MODELS:
            stmt = delete(model).where(
                model.is_deleted.is_(True),
                model.deleted_at.is_not(None),
                model.deleted_at < cutoff,
            )
            result = await session.execute(stmt)
            deleted[model.__tablename__] = int(result.rowcount or 0)

        # Customers: only purge when no live Leads/Deals still reference them.
        blocked_subquery = select(Customer.id).where(
            Customer.is_deleted.is_(True),
            Customer.deleted_at.is_not(None),
            Customer.deleted_at < cutoff,
            exists().where((Lead.customer_id == Customer.id) & Lead.is_deleted.is_(False))
            | exists().where((Deal.customer_id == Customer.id) & Deal.is_deleted.is_(False)),
        )
        blocked_count = len((await session.execute(blocked_subquery)).scalars().all())

        customer_stmt = delete(Customer).where(
            Customer.is_deleted.is_(True),
            Customer.deleted_at.is_not(None),
            Customer.deleted_at < cutoff,
            ~exists().where((Lead.customer_id == Customer.id) & Lead.is_deleted.is_(False)),
            ~exists().where((Deal.customer_id == Customer.id) & Deal.is_deleted.is_(False)),
        )
        result = await session.execute(customer_stmt)
        deleted[Customer.__tablename__] = int(result.rowcount or 0)

        return deleted, blocked_count

    async def purge_public_users(self, session, cutoff: datetime) -> int:
        """Purge expired soft-deleted rows from the shared public `users` table.

        Call once per run, AFTER `clear_tenant_schema`, never inside the org loop.
        Does not commit.
        """
        result = await session.execute(
            delete(User).where(
                User.is_deleted.is_(True),
                User.deleted_at.is_not(None),
                User.deleted_at < cutoff,
            )
        )
        return int(result.rowcount or 0)
