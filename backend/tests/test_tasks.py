from datetime import UTC, datetime, timedelta

import pytest


@pytest.mark.asyncio
async def test_task_crud_flow(client, auth_headers):
    create_response = await client.post(
        "/api/v1/tasks",
        headers=auth_headers,
        json={
            "title": "Send onboarding deck",
            "description": "Email the standard onboarding deck to the customer.",
            "due_date": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
            "priority": "medium",
            "status": "pending",
        },
    )
    assert create_response.status_code == 201
    task = create_response.json()
    task_id = task["id"]
    assert task["status"] == "pending"

    list_response = await client.get("/api/v1/tasks?page=1&page_size=10", headers=auth_headers)
    assert list_response.status_code == 200
    listed = list_response.json()
    assert listed["pagination"]["total"] == 1
    assert listed["items"][0]["id"] == task_id

    update_response = await client.put(
        f"/api/v1/tasks/{task_id}",
        headers=auth_headers,
        json={"status": "in_progress", "priority": "high"},
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["status"] == "in_progress"
    assert updated["priority"] == "high"

    delete_response = await client.delete(f"/api/v1/tasks/{task_id}", headers=auth_headers)
    assert delete_response.status_code == 200
    assert delete_response.json()["message"] == "Task deleted successfully."

    after_delete = await client.get("/api/v1/tasks?page=1&page_size=10", headers=auth_headers)
    assert after_delete.status_code == 200
    assert after_delete.json()["pagination"]["total"] == 0


@pytest.mark.asyncio
async def test_task_filter_by_status(client, auth_headers):
    base = {
        "due_date": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        "priority": "low",
    }
    for status_value in ["pending", "in_progress", "completed"]:
        response = await client.post(
            "/api/v1/tasks",
            headers=auth_headers,
            json={**base, "title": f"task-{status_value}", "status": status_value},
        )
        assert response.status_code == 201

    pending_only = await client.get(
        "/api/v1/tasks?status=pending&page=1&page_size=10",
        headers=auth_headers,
    )
    assert pending_only.status_code == 200
    body = pending_only.json()
    assert body["pagination"]["total"] == 1
    assert body["items"][0]["status"] == "pending"
