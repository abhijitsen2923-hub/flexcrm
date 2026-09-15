from datetime import UTC, datetime
from datetime import date as _date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissions
from app.core.permissions import PermissionCode
from app.core.tenancy import current_org
from app.database.session import get_db_session
from app.hr.models import EmployeeProfile, PerformanceSnapshot
from app.models.organization import Organization
from app.hr.schemas import (
    EmployeeProfileRead,
    EmployeeProfileUpdate,
    PerformanceSnapshotRead,
    ScorecardRow,
    TeamScorecard,
)
from app.hr.services import ScorecardService
from app.models.user import User


router = APIRouter()


@router.get("/scorecards", response_model=TeamScorecard)
async def team_scorecard(
    snapshot_date: _date | None = Query(default=None),
    _: object = Depends(require_permissions(PermissionCode.HR_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    """Latest snapshot per user (defaults to whatever the most recent run wrote)."""
    target_date = snapshot_date or (
        await session.execute(select(PerformanceSnapshot.snapshot_date).order_by(PerformanceSnapshot.snapshot_date.desc()).limit(1))
    ).scalar_one_or_none()

    if target_date is None:
        return TeamScorecard(snapshot_date=_date.today(), rows=[])

    snapshots = (
        await session.execute(
            select(PerformanceSnapshot, User)
            .join(User, User.id == PerformanceSnapshot.user_id)
            .where(PerformanceSnapshot.snapshot_date == target_date)
            .order_by(PerformanceSnapshot.score.desc())
        )
    ).all()

    rows = [
        ScorecardRow(
            user_id=snap.user_id,
            user_name=f"{user.first_name} {user.last_name}",
            deals_closed=snap.deals_closed,
            revenue=snap.revenue,
            collections=snap.collections,
            conversion_rate=snap.conversion_rate,
            call_activity=snap.call_activity,
            score=snap.score,
            grade=snap.grade,
        )
        for snap, user in snapshots
    ]
    return TeamScorecard(snapshot_date=target_date, rows=rows)


@router.get("/scorecards/{user_id}", response_model=list[PerformanceSnapshotRead])
async def individual_scorecard(
    user_id: UUID,
    _: object = Depends(require_permissions(PermissionCode.HR_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    rows = (
        await session.execute(
            select(PerformanceSnapshot)
            .where(PerformanceSnapshot.user_id == user_id)
            .order_by(PerformanceSnapshot.snapshot_date.desc())
            .limit(60)
        )
    ).scalars().all()
    return list(rows)


@router.post("/scorecards/{user_id}/recompute", response_model=PerformanceSnapshotRead)
async def recompute_user(
    user_id: UUID,
    _: object = Depends(require_permissions(PermissionCode.HR_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    service = ScorecardService(session)
    # Mirror the nightly job: fold in call activity only when this org uses Callyzer.
    org_id = current_org(session)
    features = (
        await session.execute(select(Organization.features).where(Organization.id == org_id))
    ).scalar_one_or_none() or {}
    call_activity = None
    if features.get("module.callyzer"):
        now = datetime.now(UTC)
        month_start = datetime(now.year, now.month, 1, tzinfo=UTC)
        scores = await service.call_activity_scores(date_from=month_start, date_to=now)
        call_activity = scores.get(user_id, Decimal("0"))
    snapshot = await service.compute_user(user_id, call_activity=call_activity)
    await service.commit()
    return snapshot


@router.get("/employees/{user_id}", response_model=EmployeeProfileRead)
async def get_employee(
    user_id: UUID,
    _: object = Depends(require_permissions(PermissionCode.HR_VIEW)),
    session: AsyncSession = Depends(get_db_session),
):
    profile = (
        await session.execute(select(EmployeeProfile).where(EmployeeProfile.user_id == user_id))
    ).scalar_one_or_none()
    if profile is None:
        # Lazy-create so the GET surface is symmetric.
        profile = EmployeeProfile(user_id=user_id)
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
    return profile


@router.patch("/employees/{user_id}", response_model=EmployeeProfileRead)
async def update_employee(
    user_id: UUID,
    payload: EmployeeProfileUpdate,
    _: object = Depends(require_permissions(PermissionCode.HR_MANAGE)),
    session: AsyncSession = Depends(get_db_session),
):
    profile = (
        await session.execute(select(EmployeeProfile).where(EmployeeProfile.user_id == user_id))
    ).scalar_one_or_none()
    if profile is None:
        profile = EmployeeProfile(user_id=user_id)
        session.add(profile)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    await session.commit()
    await session.refresh(profile)
    return profile
