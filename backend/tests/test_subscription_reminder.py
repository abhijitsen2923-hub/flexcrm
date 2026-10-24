import pytest
from app.core.security import create_access_token
from app.database.enums import UserRole, UserStatus
from app.database.session import db_manager
from app.models.user import User


@pytest.mark.asyncio
async def test_subscription_reminder_lifecycle(client):
    # 1. Register a client tenant
    reg_res = await client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Tenant",
            "last_name": "Admin",
            "email": "tenant.sub@example.com",
            "password": "StrongPassword123!",
            "role": "owner",
            "organization_name": "Acme Real Estate",
            "business_type": "real_estate",
        },
    )
    assert reg_res.status_code == 201, reg_res.text
    tenant_token = reg_res.json()["access_token"]
    tenant_headers = {"Authorization": f"Bearer {tenant_token}"}

    # Verify initial subscription config
    me_res = await client.get("/api/v1/organizations/me", headers=tenant_headers)
    assert me_res.status_code == 200
    me_data = me_res.json()
    org_id = me_data["id"]
    assert me_data["subscription"] is not None
    assert me_data["subscription"]["reminder_enabled"] is False

    # 2. Non-platform admin cannot access admin endpoint
    patch_res = await client.patch(
        f"/api/v1/admin/organizations/{org_id}/subscription",
        headers=tenant_headers,
        json={
            "reminder_enabled": True,
            "end_date": "2026-11-01",
            "provider_contact": "billing@flexcrm.io | +91 99999 88888",
        },
    )
    assert patch_res.status_code == 403

    # 3. Create a platform admin user and mint platform admin token
    async with db_manager.session_factory() as session:
        platform_user = User(
            email="platform.superadmin@flexcrm.local",
            password_hash="fakehash",
            first_name="Super",
            last_name="Admin",
            role=UserRole.owner,
            status=UserStatus.active,
            is_platform_admin=True,
        )
        session.add(platform_user)
        await session.commit()
        await session.refresh(platform_user)
        admin_id = platform_user.id

    admin_token, _ = create_access_token(
        subject=str(admin_id),
        role=UserRole.owner.value,
        is_platform_admin=True,
    )
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 4. Platform admin updates subscription reminder
    admin_patch_res = await client.patch(
        f"/api/v1/admin/organizations/{org_id}/subscription",
        headers=admin_headers,
        json={
            "reminder_enabled": True,
            "end_date": "2026-11-01",
            "provider_contact": "billing@flexcrm.io | +91 99999 88888",
        },
    )
    assert admin_patch_res.status_code == 200, admin_patch_res.text
    admin_patch_data = admin_patch_res.json()
    assert admin_patch_data["subscription"]["reminder_enabled"] is True
    assert admin_patch_data["subscription"]["end_date"] == "2026-11-01"
    assert admin_patch_data["subscription"]["provider_contact"] == "billing@flexcrm.io | +91 99999 88888"

    # 5. Tenant fetches /organizations/me and sees the updated subscription reminder
    me_res_after = await client.get("/api/v1/organizations/me", headers=tenant_headers)
    assert me_res_after.status_code == 200
    me_data_after = me_res_after.json()
    assert me_data_after["subscription"]["reminder_enabled"] is True
    assert me_data_after["subscription"]["end_date"] == "2026-11-01"
    assert me_data_after["subscription"]["provider_contact"] == "billing@flexcrm.io | +91 99999 88888"

