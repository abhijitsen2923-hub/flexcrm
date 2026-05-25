from datetime import UTC, datetime, timedelta

import pytest


@pytest.mark.asyncio
async def test_deal_crud_flow(client, auth_headers):
    customer_response = await client.post(
        "/api/v1/customers",
        headers=auth_headers,
        json={
            "company_name": "Pied Piper",
            "contact_name": "Richard Hendricks",
            "email": "richard@pp.example",
            "phone": "+15557778888",
            "address": "Erlich's Garage",
            "source": "referral",
            "status": "active",
        },
    )
    assert customer_response.status_code == 201
    customer_id = customer_response.json()["id"]

    create_response = await client.post(
        "/api/v1/deals",
        headers=auth_headers,
        json={
            "customer_id": customer_id,
            "title": "Compression deal",
            "amount": "75000",
            "stage": "proposal",
            "expected_close": (datetime.now(UTC) + timedelta(days=30)).date().isoformat(),
            "status": "open",
        },
    )
    assert create_response.status_code == 201
    deal = create_response.json()
    deal_id = deal["id"]
    from decimal import Decimal
    # Decimal columns serialize with their stored scale ("75000.00", not "75000").
    assert Decimal(deal["amount"]) == Decimal("75000")

    list_response = await client.get("/api/v1/deals?page=1&page_size=10", headers=auth_headers)
    assert list_response.status_code == 200
    listed = list_response.json()
    assert listed["pagination"]["total"] == 1

    update_response = await client.put(
        f"/api/v1/deals/{deal_id}",
        headers=auth_headers,
        json={"stage": "negotiation", "amount": "90000"},
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["stage"] == "negotiation"
    assert Decimal(updated["amount"]) == Decimal("90000")

    delete_response = await client.delete(f"/api/v1/deals/{deal_id}", headers=auth_headers)
    assert delete_response.status_code == 200
    assert delete_response.json()["message"] == "Deal deleted successfully."

    after_delete = await client.get("/api/v1/deals?page=1&page_size=10", headers=auth_headers)
    assert after_delete.status_code == 200
    assert after_delete.json()["pagination"]["total"] == 0


@pytest.mark.asyncio
async def test_deal_amount_must_be_non_negative(client, auth_headers):
    customer_response = await client.post(
        "/api/v1/customers",
        headers=auth_headers,
        json={
            "company_name": "Aviato",
            "contact_name": "Erlich Bachman",
            "email": "erlich@aviato.example",
            "phone": "+15558889999",
            "address": "Same garage",
            "source": "referral",
            "status": "active",
        },
    )
    customer_id = customer_response.json()["id"]

    invalid_response = await client.post(
        "/api/v1/deals",
        headers=auth_headers,
        json={
            "customer_id": customer_id,
            "title": "Negative amount",
            "amount": "-100",
            "stage": "proposal",
            "expected_close": (datetime.now(UTC) + timedelta(days=7)).date().isoformat(),
            "status": "open",
        },
    )
    assert invalid_response.status_code in {400, 409, 422}
