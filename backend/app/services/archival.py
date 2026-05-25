from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, exists, select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.database.session import db_manager
from app.models import Activity, Customer, Deal, Lead, Notification, Task, User


logger = get_logger(__name__)


@dataclass
class ArchivalReport:
    cutoff: datetime
    deleted: dict[str, int] = field(default_factory=dict)
    skipped_customers: int = 0


class ArchivalService:
    """Hard-delete rows that have been soft-deleted for longer than the retention window.

    Designed to be run on a schedule (cron, Kubernetes CronJob, etc.) via
    `python -m app.jobs.archive` — see `backend/scripts/archive_soft_deleted.py`.

    Deletion order respects RESTRICT FKs:
    Notification, Activity, Task → Lead, Deal → Customer → User.
    Customers with any live (non-soft-deleted) Lead or Deal referencing them
    are skipped to avoid breaking RESTRICT.
    """

    async def purge_expired(self, retention_days: int | None = None) -> ArchivalReport:
        settings = get_settings()
        days = retention_days if retention_days is not None else settings.archival_retention_days
        if days <= 0:
            logger.info("Archival skipped: retention_days <= 0")
            return ArchivalReport(cutoff=datetime.now(UTC))

        cutoff = datetime.now(UTC) - timedelta(days=days)
        report = ArchivalReport(cutoff=cutoff)

        async with db_manager.session_factory() as session:
            # Order matters — see class docstring.
            for model in (Notification, Activity, Task, Lead, Deal):
                stmt = delete(model).where(
                    model.is_deleted.is_(True),
                    model.deleted_at.is_not(None),
                    model.deleted_at < cutoff,
                )
                result = await session.execute(stmt)
                report.deleted[model.__tablename__] = int(result.rowcount or 0)

            # Customers: only purge when no live Leads/Deals still reference them.
            blocked_subquery = select(Customer.id).where(
                Customer.is_deleted.is_(True),
                Customer.deleted_at.is_not(None),
                Customer.deleted_at < cutoff,
                exists().where(
                    (Lead.customer_id == Customer.id) & Lead.is_deleted.is_(False)
                )
                | exists().where(
                    (Deal.customer_id == Customer.id) & Deal.is_deleted.is_(False)
                ),
            )
            blocked_count = len((await session.execute(blocked_subquery)).scalars().all())
            report.skipped_customers = blocked_count

            customer_stmt = delete(Customer).where(
                Customer.is_deleted.is_(True),
                Customer.deleted_at.is_not(None),
                Customer.deleted_at < cutoff,
                ~exists().where(
                    (Lead.customer_id == Customer.id) & Lead.is_deleted.is_(False)
                ),
                ~exists().where(
                    (Deal.customer_id == Customer.id) & Deal.is_deleted.is_(False)
                ),
            )
            result = await session.execute(customer_stmt)
            report.deleted[Customer.__tablename__] = int(result.rowcount or 0)

            user_stmt = delete(User).where(
                User.is_deleted.is_(True),
                User.deleted_at.is_not(None),
                User.deleted_at < cutoff,
            )
            result = await session.execute(user_stmt)
            report.deleted[User.__tablename__] = int(result.rowcount or 0)

            await session.commit()

        logger.info(
            "Archival completed",
            extra={
                "cutoff": cutoff.isoformat(),
                "deleted": report.deleted,
                "skipped_customers": report.skipped_customers,
            },
        )
        return report


archival_service = ArchivalService()
