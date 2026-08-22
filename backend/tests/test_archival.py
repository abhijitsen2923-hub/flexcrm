from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select, update

from app.database.session import db_manager
from app.jobs.archive import dispatch_archival
from app.models import Activity, Customer, Task


async def _run_archival(retention_days: int):
    """Run the real cross-org archival dispatch — the same entry point the CLI
    (`python -m app.jobs.archive`) and `POST /cron/archive` use, so these tests
    cover the per-org loop and not just the raw delete statements."""
    async with db_manager.session_factory() as session:
        return await dispatch_archival(session, retention_days=retention_days)


async def _create_customer(client, headers, *, company_name: str) -> str:
    response = await client.post(
        "/api/v1/customers",
        headers=headers,
        json={
            "company_name": company_name,
            "contact_name": "Archival Tester",
            "email": f"{company_name.lower().replace(' ', '')}@example.com",
            "phone": "+15550000000",
            "address": "n/a",
            "source": "referral",
            "status": "prospect",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _create_task(client, headers, *, title: str) -> str:
    response = await client.post(
        "/api/v1/tasks",
        headers=headers,
        json={
            "title": title,
            "description": "",
            "due_date": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "priority": "low",
            "status": "pending",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _backdate_deleted_at(model, row_id: str, when: datetime) -> None:
    async with db_manager.session_factory() as session:
        await session.execute(
            update(model).where(model.id == UUID(row_id)).values(deleted_at=when)
        )
        await session.commit()


async def _force_soft_delete(model, row_id: str, when: datetime) -> None:
    """Mark a row soft-deleted at a specific past timestamp, bypassing the API.

    Used for tables whose REST surface doesn't expose a delete (e.g. activities).
    """
    async with db_manager.session_factory() as session:
        await session.execute(
            update(model)
            .where(model.id == UUID(row_id))
            .values(is_deleted=True, deleted_at=when)
        )
        await session.commit()


@pytest.mark.asyncio
async def test_archival_hard_deletes_only_expired_rows(client, auth_headers):
    fresh_customer_id = await _create_customer(client, auth_headers, company_name="Fresh Co")
    old_customer_id = await _create_customer(client, auth_headers, company_name="Old Co")

    assert (await client.delete(f"/api/v1/customers/{fresh_customer_id}", headers=auth_headers)).status_code == 200
    assert (await client.delete(f"/api/v1/customers/{old_customer_id}", headers=auth_headers)).status_code == 200

    await _backdate_deleted_at(Customer, old_customer_id, datetime.now(UTC) - timedelta(days=120))

    report = await _run_archival(90)
    assert report.deleted["customers"] == 1
    assert report.skipped_customers == 0

    async with db_manager.session_factory() as session:
        remaining_ids = {
            str(row) for row in (await session.execute(select(Customer.id))).scalars().all()
        }
    assert old_customer_id not in remaining_ids
    assert fresh_customer_id in remaining_ids


@pytest.mark.asyncio
async def test_archival_skips_customers_with_live_children(client, auth_headers):
    customer_id = await _create_customer(client, auth_headers, company_name="Skippy")

    lead_response = await client.post(
        "/api/v1/leads",
        headers=auth_headers,
        json={
            "customer_id": customer_id,
            "industry": "education",
            "title": "Live lead",
            "contact_name": "Live Lead Contact",
            "contact_phone": "+919900300001",
            "value": "100",
            "probability": 10,
            "expected_close_date": (datetime.now(UTC) + timedelta(days=7)).date().isoformat(),
        },
    )
    assert lead_response.status_code == 201

    assert (await client.delete(f"/api/v1/customers/{customer_id}", headers=auth_headers)).status_code == 200
    await _backdate_deleted_at(Customer, customer_id, datetime.now(UTC) - timedelta(days=120))

    report = await _run_archival(90)
    assert report.deleted.get("customers", 0) == 0
    assert report.skipped_customers == 1

    async with db_manager.session_factory() as session:
        remaining_ids = {
            str(row) for row in (await session.execute(select(Customer.id))).scalars().all()
        }
    assert customer_id in remaining_ids


@pytest.mark.asyncio
async def test_archival_purges_tasks_and_activities(client, auth_headers):
    customer_id = await _create_customer(client, auth_headers, company_name="Cleanup Co")

    activity_response = await client.post(
        "/api/v1/activities",
        headers=auth_headers,
        json={"customer_id": customer_id, "type": "note", "note": "Old note"},
    )
    assert activity_response.status_code == 201
    activity_id = activity_response.json()["id"]

    task_id = await _create_task(client, auth_headers, title="Old task")
    assert (await client.delete(f"/api/v1/tasks/{task_id}", headers=auth_headers)).status_code == 200

    backdate = datetime.now(UTC) - timedelta(days=120)
    await _force_soft_delete(Activity, activity_id, backdate)
    await _backdate_deleted_at(Task, task_id, backdate)

    report = await _run_archival(90)
    assert report.deleted["tasks"] == 1
    assert report.deleted["activities"] == 1

    async with db_manager.session_factory() as session:
        remaining_tasks = {
            str(row) for row in (await session.execute(select(Task.id))).scalars().all()
        }
        remaining_activities = {
            str(row) for row in (await session.execute(select(Activity.id))).scalars().all()
        }
    assert task_id not in remaining_tasks
    assert activity_id not in remaining_activities


@pytest.mark.asyncio
async def test_archival_zero_retention_is_a_noop(client, auth_headers):
    customer_id = await _create_customer(client, auth_headers, company_name="Noop Co")
    assert (await client.delete(f"/api/v1/customers/{customer_id}", headers=auth_headers)).status_code == 200
    await _backdate_deleted_at(Customer, customer_id, datetime.now(UTC) - timedelta(days=999))

    report = await _run_archival(0)
    assert report.deleted == {}

    async with db_manager.session_factory() as session:
        still_there = (
            await session.execute(select(Customer.id).where(Customer.id == UUID(customer_id)))
        ).scalar_one_or_none()
    assert still_there is not None
