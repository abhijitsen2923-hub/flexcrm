from datetime import UTC, datetime, timedelta

import pytest


@pytest.mark.asyncio
async def test_dashboard_and_analytics_endpoints(client, auth_headers):
    customer_response = await client.post(
        "/api/v1/customers",
        headers=auth_headers,
        json={
            "company_name": "Northwind Traders",
            "contact_name": "Avery Lee",
            "email": "avery@northwind.example",
            "phone": "+15552223333",
            "address": "42 River Road",
            "source": "google_ads",
            "status": "active",
        },
    )
    assert customer_response.status_code == 201
    customer_id = customer_response.json()["id"]

    qualified_lead_response = await client.post(
        "/api/v1/leads",
        headers=auth_headers,
        json={
            "customer_id": customer_id,
            "industry": "education",
            "title": "Platform expansion",
            "contact_name": "Platform Contact",
            "contact_phone": "+919900400001",
            "value": "25000",
            "probability": 60,
            "expected_close_date": (datetime.now(UTC) + timedelta(days=14)).date().isoformat(),
        },
    )
    assert qualified_lead_response.status_code == 201
    qualified_lead_id = qualified_lead_response.json()["id"]

    # Advance through Stage 1 → Qualified via the transitions endpoint so the
    # active-leads count matches expectations.
    advance = await client.post(
        f"/api/v1/leads/{qualified_lead_id}/transitions",
        headers=auth_headers,
        json={
            "to_stage_code": "qualified",
            "comment": "Budget, interest & decision authority verified.",
        },
    )
    assert advance.status_code == 201, advance.text

    won_lead_response = await client.post(
        "/api/v1/leads",
        headers=auth_headers,
        json={
            "customer_id": customer_id,
            "industry": "education",
            "title": "Renewal",
            "contact_name": "Renewal Contact",
            "contact_phone": "+919900400002",
            "value": "10000",
            "probability": 100,
            "expected_close_date": (datetime.now(UTC) + timedelta(days=7)).date().isoformat(),
        },
    )
    assert won_lead_response.status_code == 201
    won_lead_id = won_lead_response.json()["id"]

    win = await client.post(
        f"/api/v1/leads/{won_lead_id}/transitions",
        headers=auth_headers,
        json={
            "to_stage_code": "sold",
            "comment": "Fee paid — admission confirmed. Closed-won.",
        },
    )
    assert win.status_code == 201, win.text

    won_deal_response = await client.post(
        "/api/v1/deals",
        headers=auth_headers,
        json={
            "customer_id": customer_id,
            "title": "Annual contract",
            "amount": "50000",
            "stage": "closed_won",
            "expected_close": datetime.now(UTC).date().isoformat(),
            "status": "won",
        },
    )
    assert won_deal_response.status_code == 201

    open_deal_response = await client.post(
        "/api/v1/deals",
        headers=auth_headers,
        json={
            "customer_id": customer_id,
            "title": "Upsell package",
            "amount": "15000",
            "stage": "proposal",
            "expected_close": (datetime.now(UTC) + timedelta(days=30)).date().isoformat(),
            "status": "open",
        },
    )
    assert open_deal_response.status_code == 201

    overdue_task_response = await client.post(
        "/api/v1/tasks",
        headers=auth_headers,
        json={
            "title": "Follow up on onboarding",
            "description": "Confirm customer rollout checklist",
            "due_date": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
            "priority": "high",
            "status": "pending",
        },
    )
    assert overdue_task_response.status_code == 201

    activity_response = await client.post(
        "/api/v1/activities",
        headers=auth_headers,
        json={
            "customer_id": customer_id,
            "type": "meeting",
            "note": "Kickoff call completed with procurement team.",
        },
    )
    assert activity_response.status_code == 201

    summary_response = await client.get("/api/v1/dashboard/summary", headers=auth_headers)
    assert summary_response.status_code == 200
    summary_payload = summary_response.json()
    assert summary_payload["total_customers"] == 1
    assert summary_payload["active_leads"] == 1
    assert summary_payload["overdue_tasks"] == 1

    charts_response = await client.get("/api/v1/dashboard/charts", headers=auth_headers)
    assert charts_response.status_code == 200
    charts_payload = charts_response.json()
    assert charts_payload["lead_stage_breakdown"]
    assert charts_payload["task_status_breakdown"]

    recent_response = await client.get("/api/v1/dashboard/recent-activities", headers=auth_headers)
    assert recent_response.status_code == 200
    assert recent_response.json()["items"][0]["customer_name"] == "Northwind Traders"

    revenue_response = await client.get("/api/v1/analytics/revenue", headers=auth_headers)
    assert revenue_response.status_code == 200
    revenue_payload = revenue_response.json()
    # Decimal columns serialize with their stored scale ("50000.00", not "50000"),
    # so compare by value rather than string.
    from decimal import Decimal
    assert Decimal(revenue_payload["total_closed_revenue"]) == Decimal("50000")
    assert Decimal(revenue_payload["open_pipeline_value"]) == Decimal("15000")

    leads_response = await client.get("/api/v1/analytics/leads", headers=auth_headers)
    assert leads_response.status_code == 200
    leads_payload = leads_response.json()
    assert leads_payload["total_leads"] == 2
    assert leads_payload["won_leads"] == 1

    conversion_response = await client.get("/api/v1/analytics/conversion", headers=auth_headers)
    assert conversion_response.status_code == 200
    conversion_payload = conversion_response.json()
    assert conversion_payload["lead_to_win_rate"] == 50
    assert conversion_payload["deal_win_rate"] == 50
