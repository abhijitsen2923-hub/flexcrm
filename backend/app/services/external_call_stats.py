"""Per-employee aggregation over synced ExternalCall rows.

Powers the Calls → Performance tab AND the HR scorecard's call-activity factor
(the two share one query so the numbers always agree). Runs in the caller's tenant
schema (external_calls is tenant-scoped); employee names resolve from public.users,
org-filtered because that table is shared across every tenant.

Calls are grouped by the matched FlexCRM user when one exists, else by the raw
device number — so an UNMATCHED device number still shows (flagged), and a user who
dialled from two devices merges into one row.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import String, cast, func, select

from app.core.tenancy import current_org
from app.models.external_call import ExternalCall
from app.models.user import User
from app.schemas.callyzer import (
    CallStatsResponse,
    CallStatsTotals,
    CallTrendPoint,
    CallTrendResponse,
    EmployeeCallStats,
)
from app.services.base import ServiceBase


class ExternalCallStatsService(ServiceBase):
    async def employee_stats(
        self,
        *,
        date_from: datetime,
        date_to: datetime,
        owner_user_id: UUID | None = None,
    ) -> CallStatsResponse:
        """Aggregate calls in [date_from, date_to] per employee. When owner_user_id is
        given (a rep viewing their own numbers), only that user's calls are counted."""
        # Group matched users by user_id, unmatched device numbers by emp_number.
        key = func.coalesce(cast(ExternalCall.user_id, String), ExternalCall.emp_number)
        conds = [ExternalCall.call_at >= date_from, ExternalCall.call_at <= date_to]
        if owner_user_id is not None:
            conds.append(ExternalCall.user_id == owner_user_id)

        stmt = (
            select(
                key.label("key"),
                func.max(ExternalCall.user_id).label("user_id"),  # constant within a matched group
                func.max(ExternalCall.emp_number).label("emp_number"),
                func.max(ExternalCall.emp_name).label("emp_name"),
                func.count().label("total"),
                func.count().filter(ExternalCall.call_type == "Outgoing").label("outgoing"),
                func.count().filter(ExternalCall.call_type == "Incoming").label("incoming"),
                func.count().filter(ExternalCall.call_type == "Missed").label("missed"),
                func.count().filter(ExternalCall.call_type == "Rejected").label("rejected"),
                func.count().filter(ExternalCall.duration_seconds > 0).label("connected"),
                func.coalesce(func.sum(ExternalCall.duration_seconds), 0).label("talk"),
                func.count(func.distinct(ExternalCall.client_number_key)).label("clients"),
                func.max(ExternalCall.call_at).label("last_call_at"),
            )
            .where(*conds)
            .group_by(key)
        )
        rows = (await self.session.execute(stmt)).all()

        # Resolve matched user_ids → display name (public.users, org-filtered).
        user_ids = [r.user_id for r in rows if r.user_id is not None]
        names: dict[UUID, str] = {}
        if user_ids:
            org_id = current_org(self.session)
            urows = (
                await self.session.execute(
                    select(User.id, User.first_name, User.last_name).where(
                        User.organization_id == org_id, User.id.in_(user_ids)
                    )
                )
            ).all()
            names = {
                uid: (f"{(fn or '').strip()} {(ln or '').strip()}".strip() or "")
                for uid, fn, ln in urows
            }

        stats: list[EmployeeCallStats] = []
        for r in rows:
            total = int(r.total or 0)
            connected = int(r.connected or 0)
            talk = int(r.talk or 0)
            matched = r.user_id is not None
            name = (names.get(r.user_id) if matched else None) or r.emp_name or r.emp_number or "Unknown"
            stats.append(
                EmployeeCallStats(
                    user_id=r.user_id,
                    name=name,
                    emp_number=r.emp_number,
                    unmatched=not matched,
                    total=total,
                    outgoing=int(r.outgoing or 0),
                    incoming=int(r.incoming or 0),
                    missed=int(r.missed or 0),
                    rejected=int(r.rejected or 0),
                    connected=connected,
                    connect_rate=round(connected / total, 4) if total else 0.0,
                    total_talk_seconds=talk,
                    avg_talk_seconds=round(talk / connected) if connected else 0,
                    unique_clients=int(r.clients or 0),
                    last_call_at=r.last_call_at,
                )
            )
        stats.sort(key=lambda s: s.total, reverse=True)

        # Team-wide distinct clients (rows can share a client, so this is NOT a sum).
        team_clients = int(
            (
                await self.session.execute(
                    select(func.count(func.distinct(ExternalCall.client_number_key))).where(*conds)
                )
            ).scalar_one()
            or 0
        )
        totals = CallStatsTotals(
            callers=len(stats),
            total=sum(s.total for s in stats),
            connected=sum(s.connected for s in stats),
            missed=sum(s.missed for s in stats),
            total_talk_seconds=sum(s.total_talk_seconds for s in stats),
            unique_clients=team_clients,
        )
        return CallStatsResponse(date_from=date_from, date_to=date_to, totals=totals, rows=stats)

    async def daily_trend(
        self, *, user_id: UUID, date_from: datetime, date_to: datetime
    ) -> CallTrendResponse:
        """Per-day call counts for ONE user over the window — the Performance drill-down.
        Buckets by IST calendar day (call_at is stored as a true UTC instant)."""
        day = func.date(func.timezone("Asia/Kolkata", ExternalCall.call_at)).label("day")
        stmt = (
            select(
                day,
                func.count().label("calls"),
                func.count().filter(ExternalCall.duration_seconds > 0).label("connected"),
                func.count().filter(ExternalCall.call_type == "Missed").label("missed"),
            )
            .where(
                ExternalCall.user_id == user_id,
                ExternalCall.call_at >= date_from,
                ExternalCall.call_at <= date_to,
            )
            .group_by(day)
            .order_by(day)
        )
        rows = (await self.session.execute(stmt)).all()
        points = [
            CallTrendPoint(
                date=r.day,
                calls=int(r.calls or 0),
                connected=int(r.connected or 0),
                missed=int(r.missed or 0),
            )
            for r in rows
        ]
        return CallTrendResponse(user_id=user_id, date_from=date_from, date_to=date_to, points=points)
