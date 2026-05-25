import pytest


@pytest.mark.asyncio
async def test_customer_crud_flow(client, auth_headers):
    create_response = await client.post(
        "/api/v1/customers",
        headers=auth_headers,
        json={
            "company_name": "Acme Corp",
            "contact_name": "Jordan Miles",
            "email": "jordan@acme.example",
            "phone": "+15551112222",
            "address": "100 Market Street",
            "source": "referral",
            "status": "prospect",
        },
    )
    assert create_response.status_code == 201
    customer = create_response.json()
    customer_id = customer["id"]

    list_response = await client.get("/api/v1/customers?page=1&page_size=10", headers=auth_headers)
    assert list_response.status_code == 200
    listed_payload = list_response.json()
    assert listed_payload["pagination"]["total"] == 1
    assert listed_payload["items"][0]["company_name"] == "Acme Corp"

    detail_response = await client.get(f"/api/v1/customers/{customer_id}", headers=auth_headers)
    assert detail_response.status_code == 200
    assert detail_response.json()["contact_name"] == "Jordan Miles"

    update_response = await client.put(
        f"/api/v1/customers/{customer_id}",
        headers=auth_headers,
        json={"status": "active", "source": "website"},
    )
    assert update_response.status_code == 200
    updated_customer = update_response.json()
    assert updated_customer["status"] == "active"
    assert updated_customer["source"] == "website"

    delete_response = await client.delete(f"/api/v1/customers/{customer_id}", headers=auth_headers)
    assert delete_response.status_code == 200
    assert delete_response.json()["message"] == "Customer deleted successfully."

    list_after_delete = await client.get("/api/v1/customers?page=1&page_size=10", headers=auth_headers)
    assert list_after_delete.status_code == 200
    assert list_after_delete.json()["pagination"]["total"] == 0
