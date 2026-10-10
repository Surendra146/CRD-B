import pytest

from app.models import Tenant
from app.services.security import create_token

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("tenant_claim", [None, "not-a-tenant", True, 1.5, "", 0])
def test_invalid_tenant_claim_returns_401(client, account, tenant_claim):
    token = create_token({"userId": account["user"]["id"], "tenantId": tenant_claim})
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer " + token}).status_code == 401


def test_suspended_tenant_cannot_access_api(client, account, db_session):
    tenant = db_session.get(Tenant, account["user"]["tenantId"])
    tenant.is_active = False
    db_session.commit()
    assert client.get("/api/auth/me", headers=account["headers"]).status_code == 403


def test_same_business_name_can_register_independent_tenants(client, account):
    response = client.post("/api/auth/register", json={**account["payload"], "email": "another-business@example.com"})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["tenantId"] != account["user"]["tenantId"]


def test_role_profiles_include_enterprise_defaults(client, account):
    response = client.get("/api/auth/roles", headers=account["headers"])
    assert response.status_code == 200
    assert {role["key"] for role in response.json()["data"]["customRoles"]} >= {"admin", "marketing_manager", "sales_agent", "viewer"}


def test_viewer_read_allowed_but_customer_write_denied(client, account, customer_payload):
    response = client.post("/api/auth/members", headers=account["headers"], json={
        "email": "viewer-enterprise@example.com", "password": "Viewer-password-123!", "name": "Viewer", "role": "viewer",
    })
    assert response.status_code == 200, response.text
    login = client.post("/api/auth/login", json={"email": "viewer-enterprise@example.com", "password": "Viewer-password-123!"})
    headers = {"Authorization": "Bearer " + login.json()["token"]}
    assert client.get("/api/customers/", headers=headers).status_code == 200
    assert client.post("/api/customers/", headers=headers, json=customer_payload).status_code == 403
    assert client.post("/api/auth/members", headers=headers, json={"email": "x@example.com"}).status_code == 403


def test_tenant_owner_cannot_create_platform_staff(client, account):
    response = client.post("/api/auth/members", headers=account["headers"], json={
        "email": "platform-enterprise@example.com", "password": "Staff-password-123!", "name": "Staff", "role": "platform_admin",
    })
    assert response.status_code == 400


def test_foreign_template_cannot_be_attached_to_campaign(client, account, account_factory):
    other = account_factory()
    created = client.post("/api/templates/", headers=other["headers"], json={"name": "Foreign template", "category": "marketing"})
    assert created.status_code == 200, created.text
    template_id = created.json()["data"]["id"]
    response = client.post("/api/campaigns/", headers=account["headers"], json={"name": "Campaign", "type": "broadcast", "templateId": template_id})
    assert response.status_code == 404


def test_admin_can_manage_tenant_members_but_not_other_tenant(client, account, account_factory):
    other = account_factory()
    created = client.post("/api/auth/members", headers=account["headers"], json={
        "email": "admin-enterprise@example.com", "password": "Admin-password-123!", "name": "Admin", "role": "admin",
    })
    assert created.status_code == 200
    login = client.post("/api/auth/login", json={"email": "admin-enterprise@example.com", "password": "Admin-password-123!"})
    headers = {"Authorization": "Bearer " + login.json()["token"]}
    assert client.get("/api/auth/members", headers=headers).status_code == 200
    assert client.patch(f"/api/auth/members/{other['user']['id']}", headers=headers, json={"name": "Hijacked"}).status_code == 404


def test_member_editor_updates_role_and_password(client, account):
    created = client.post("/api/auth/members", headers=account["headers"], json={
        "email": "edit-enterprise@example.com", "password": "Original-password-123!", "name": "Agent", "role": "sales_agent",
    })
    assert created.status_code == 200
    member = created.json()["data"]
    response = client.patch(f"/api/auth/members/{member['id']}", headers=account["headers"], json={
        "role": "viewer", "roleProfileName": "Viewer", "password": "Changed-password-123!",
        "allowedModules": ["customers"], "email": "edited-enterprise@example.com",
    })
    assert response.status_code == 200, response.text
    assert response.json()["data"]["role"] == "viewer"
    assert response.json()["data"]["allowedModules"] == ["customers"]
    assert client.post("/api/auth/login", json={"email": "edited-enterprise@example.com", "password": "Changed-password-123!"}).status_code == 200


def test_null_template_alias_cannot_hide_foreign_template_update(client, account, account_factory):
    other = account_factory()
    template = client.post("/api/templates/", headers=other["headers"], json={"name": "Foreign alias", "category": "marketing"}).json()["data"]
    campaign = client.post("/api/campaigns/", headers=account["headers"], json={"name": "Own campaign", "type": "broadcast"}).json()["data"]
    response = client.put(f"/api/campaigns/{campaign['id']}", headers=account["headers"], json={"template": None, "templateId": template["id"]})
    assert response.status_code == 404
    current = client.get(f"/api/campaigns/{campaign['id']}", headers=account["headers"]).json()["data"]
    assert current["templateId"] is None
