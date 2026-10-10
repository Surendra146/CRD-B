from datetime import UTC, datetime, timedelta

import pytest

from app.config.settings import get_settings
from app.models.saas import Invoice, PlatformStaff, Subscription, SubscriptionPlan
from app.services.consent import assert_send_allowed

pytestmark = pytest.mark.integration


@pytest.fixture
def plan(db_session):
    row = SubscriptionPlan(id="standard-v1", name="Configured plan", amount_minor=12000,
        currency="INR", interval="monthly", total_cycles=12, entitlements={"whatsapp_numbers": 2})
    db_session.add(row)
    db_session.commit()
    return row


@pytest.fixture
def paid(account, db_session, plan):
    row = Subscription(tenant_id=account["user"]["tenantId"], organization_id=account["user"]["organizationId"],
        plan_id=plan.id, status="active", current_start=datetime.now(UTC), current_end=datetime.now(UTC) + timedelta(days=30))
    db_session.add(row)
    db_session.commit()
    return row


def test_profile_is_created_and_isolated(client, account, account_factory):
    other = account_factory()
    assert client.get("/api/saas/profile", headers=account["headers"]).json()["data"]["legal_name"] == account["payload"]["companyName"]
    response = client.put("/api/saas/profile", headers=account["headers"], json={"legal_name": "Changed company", "tax_id": "GST-EXAMPLE"})
    assert response.status_code == 200
    assert client.get("/api/saas/profile", headers=other["headers"]).json()["data"]["legal_name"] != "Changed company"


def test_tenant_owner_is_not_platform_staff(client, account):
    assert client.get("/api/platform/overview", headers=account["headers"]).status_code == 403
    assert client.post("/api/platform/plans", headers=account["headers"], json={}).status_code == 403


def test_staff_dashboard_requires_explicit_permission(client, account, db_session):
    db_session.add(PlatformStaff(user_id=account["user"]["id"], permissions=["tenants.read"]))
    db_session.commit()
    assert client.get("/api/platform/overview", headers=account["headers"]).status_code == 200
    assert client.get("/api/platform/audit", headers=account["headers"]).status_code == 403


def test_plan_catalog_does_not_expose_provider_credentials(client, account, plan):
    response = client.get("/api/saas/plans", headers=account["headers"])
    assert response.status_code == 200
    row = response.json()["data"][0]
    assert row["amount_minor"] == 12000
    assert "provider_plan_id" not in row
    assert "secret" not in response.text


def test_invoice_history_remains_tenant_scoped(client, account, db_session, account_factory):
    other = account_factory()
    row = Invoice(tenant_id=account["user"]["tenantId"], organization_id=account["user"]["organizationId"],
        payment_reference="historical-payment", invoice_reference="historical-invoice",
        amount_minor=12000, currency="INR", status="paid", buyer_snapshot={"legal_name": "Original buyer"},
        line_items=[{"description": "Original subscription", "amount_minor": 12000}])
    db_session.add(row)
    db_session.commit()
    result = client.get("/api/saas/invoices", headers=account["headers"]).json()["data"]
    assert len(result) == 1
    assert result[0]["invoice_reference"] == "historical-invoice"
    assert result[0]["buyer_snapshot"] == {"legal_name": "Original buyer"}
    assert client.get("/api/saas/invoices", headers=other["headers"]).json()["data"] == []


def test_opt_in_requires_evidence_and_stop_prevents_send(client, account, db_session, monkeypatch):
    monkeypatch.setattr(get_settings(), "enforce_whatsapp_consent", True)
    response = client.post("/api/saas/consents", headers=account["headers"], json={"phone": "9000000000", "opted_in": True, "source": "form"})
    assert response.status_code == 400
    assert client.post("/api/saas/consents", headers=account["headers"], json={"phone": "9000000000", "opted_in": True, "source": "form", "evidence": "signed form reference"}).status_code == 200
    from fastapi import HTTPException
    with pytest.raises(HTTPException, match="approved WhatsApp template"):
        assert_send_allowed(db_session, account["user"]["tenantId"], account["user"]["organizationId"], "9000000000")
    assert client.post("/api/saas/consents", headers=account["headers"], json={"phone": "9000000000", "opted_in": False, "source": "request"}).status_code == 200
    db_session.expire_all()
    with pytest.raises(HTTPException, match="opted out"):
        assert_send_allowed(db_session, account["user"]["tenantId"], account["user"]["organizationId"], "9000000000", {"name": "approved"})


def test_onboarding_requires_subscription_and_never_accepts_api_token(client, account, paid):
    payload = {"phone": "9000000000", "business_name": "Customer company"}
    assert client.post("/api/saas/onboarding", headers=account["headers"], json=payload).status_code == 200
    assert client.post("/api/saas/onboarding", headers=account["headers"], json={**payload, "access_token": "secret"}).status_code == 422
