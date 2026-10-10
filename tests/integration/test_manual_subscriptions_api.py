from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.models.saas import AuditEvent, Invoice, PlatformStaff, Subscription, SubscriptionPlan
from app.services import billing
from tests.integration.test_saas_api import plan, paid

pytestmark = pytest.mark.integration


def grant(db, account, permissions=("subscriptions.read", "subscriptions.manage")):
    db.add(PlatformStaff(user_id=account["user"]["id"], permissions=list(permissions)))
    db.commit()


def url(account, action):
    user = account["user"]
    return f'/api/platform/tenants/{user["tenantId"]}/organizations/{user["organizationId"]}/subscription/{action}'


def assignment(plan, **changes):
    now = datetime.now(UTC)
    return {"request_id": str(uuid4()), "reason": "Approved manual plan", "plan_id": plan.id,
        "current_start": (now - timedelta(minutes=1)).isoformat(),
        "current_end": (now + timedelta(days=30)).isoformat(), **changes}


def user_for(account):
    return SimpleNamespace(tenant_id=account["user"]["tenantId"], organization_id=account["user"]["organizationId"])


@pytest.mark.parametrize("action,extra", [("assign", {}), ("renew", {"days": 30}), ("cancel", {"at_period_end": True})])
def test_mutations_require_active_explicit_platform_permission(client, account, db_session, plan, action, extra):
    data = assignment(plan) if action == "assign" else {"request_id": str(uuid4()), "reason": "Approved", **extra}
    assert client.post(url(account, action), json=data).status_code == 401
    assert client.post(url(account, action), headers=account["headers"], json=data).status_code == 403
    grant(db_session, account, ["plans.manage", "subscriptions.read"])
    assert client.post(url(account, action), headers=account["headers"], json=data).status_code == 403
    staff = db_session.get(PlatformStaff, account["user"]["id"])
    staff.permissions, staff.is_active = ["subscriptions.manage"], False
    db_session.commit()
    assert client.post(url(account, action), headers=account["headers"], json=data).status_code == 403


def test_subscription_reads_require_staff_permission(client, account, db_session):
    for endpoint in ["subscriptions", "organizations", "subscription-plans"]:
        assert client.get(f"/api/platform/{endpoint}", headers=account["headers"]).status_code == 403
    grant(db_session, account, ["subscriptions.read"])
    for endpoint in ["subscriptions", "organizations", "subscription-plans"]:
        assert client.get(f"/api/platform/{endpoint}", headers=account["headers"]).status_code == 200


def test_assignment_is_audited_idempotent_and_tenant_isolated(client, account, account_factory, db_session, plan):
    target, other = account_factory(), account_factory()
    grant(db_session, account)
    data = assignment(plan)
    response = client.post(url(target, "assign"), headers=account["headers"], json=data)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["effective_status"] == "active"
    assert client.post(url(target, "assign"), headers=account["headers"], json=data).json()["duplicate"] is True
    assert client.get("/api/saas/subscription", headers=other["headers"]).json()["data"] is None
    assert client.get("/api/saas/subscription", headers=target["headers"]).json()["data"]["plan_id"] == plan.id
    assert db_session.scalar(select(func.count()).select_from(Invoice)) == 0
    events = db_session.scalars(select(AuditEvent).where(AuditEvent.action == "platform.subscription.assign")).all()
    assert len(events) == 1
    assert events[0].actor_id == account["user"]["id"]
    assert events[0].details["target_tenant"] == target["user"]["tenantId"]
    assert events[0].details["before"] is None
    assert events[0].details["after"]["current_end"] == data["current_end"]
    assert client.post(url(target, "assign"), headers=account["headers"], json={**data, "reason": "Changed"}).status_code == 409


@pytest.mark.parametrize("action,extra", [("assign", {}), ("renew", {"days": 30}), ("cancel", {"at_period_end": False})])
def test_mismatched_target_scope_never_writes(client, account, account_factory, db_session, plan, action, extra):
    other = account_factory()
    grant(db_session, account)
    path = f'/api/platform/tenants/{account["user"]["tenantId"]}/organizations/{other["user"]["organizationId"]}/subscription/{action}'
    data = assignment(plan) if action == "assign" else {"request_id": str(uuid4()), "reason": "Approved", **extra}
    assert client.post(path, headers=account["headers"], json=data).status_code == 404
    assert db_session.scalar(select(Subscription)) is None
    assert db_session.scalar(select(AuditEvent).where(AuditEvent.action.like("platform.subscription.%"))) is None


def test_future_assignment_blocks_onboarding_and_entitlements(client, account, db_session, plan):
    grant(db_session, account)
    now = datetime.now(UTC)
    data = assignment(plan, current_start=(now + timedelta(days=1)).isoformat())
    response = client.post(url(account, "assign"), headers=account["headers"], json=data)
    assert response.json()["data"]["effective_status"] == "scheduled"
    assert client.post("/api/saas/onboarding", headers=account["headers"], json={"phone": "9000000000", "business_name": "Future"}).status_code == 402
    with pytest.raises(HTTPException) as error:
        billing.number_limit(db_session, user_for(account))
    assert error.value.status_code == 402


@pytest.mark.parametrize("expired", [False, True])
def test_renewal_extends_from_expiry_or_now_and_retry_is_safe(client, account, db_session, paid, expired):
    grant(db_session, account)
    now = datetime.now(UTC)
    if expired:
        paid.current_start, paid.current_end = now - timedelta(days=31), now - timedelta(days=1)
        db_session.commit()
    original_end = paid.current_end
    data = {"request_id": str(uuid4()), "reason": "Renewal approved", "days": 30}
    before = datetime.now(UTC)
    response = client.post(url(account, "renew"), headers=account["headers"], json=data)
    assert response.status_code == 200, response.text
    assert client.post(url(account, "renew"), headers=account["headers"], json=data).json()["duplicate"] is True
    db_session.refresh(paid)
    if expired:
        assert before + timedelta(days=30) <= paid.current_end <= datetime.now(UTC) + timedelta(days=30)
    else:
        assert paid.current_end == original_end + timedelta(days=30)
    assert billing.number_limit(db_session, user_for(account)) == 2
    assert db_session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "platform.subscription.renew")) == 1


def test_cancel_at_expiry_retains_access_then_immediate_cancel_revokes_it(client, account, db_session, paid):
    grant(db_session, account)
    original_end = paid.current_end
    data = {"request_id": str(uuid4()), "reason": "Cancellation approved", "at_period_end": True}
    assert client.post(url(account, "cancel"), headers=account["headers"], json=data).status_code == 200
    db_session.refresh(paid)
    assert paid.cancel_at_period_end and paid.current_end == original_end
    assert billing.number_limit(db_session, user_for(account)) == 2
    assert billing.effective_status(paid, original_end) == "expired"
    data = {**data, "request_id": str(uuid4()), "at_period_end": False}
    assert client.post(url(account, "cancel"), headers=account["headers"], json=data).status_code == 200
    db_session.refresh(paid)
    assert paid.current_end == original_end
    assert paid.status == "cancelled"
    with pytest.raises(HTTPException):
        billing.require_paid_subscription(db_session, user_for(account))


def test_dashboard_excludes_expired_and_future_subscriptions(client, account, db_session, paid):
    grant(db_session, account, ["tenants.read"])
    now = datetime.now(UTC)
    for start, end, expected in [(now - timedelta(days=1), now + timedelta(days=1), 1),
                                (now - timedelta(days=2), now, 0),
                                (now + timedelta(days=1), now + timedelta(days=2), 0)]:
        paid.current_start, paid.current_end = start, end
        db_session.commit()
        assert client.get("/api/platform/overview", headers=account["headers"]).json()["data"]["active_subscriptions"] == expected


def test_local_plan_creation_is_validated_and_versioned(client, account, db_session):
    grant(db_session, account, ["plans.manage"])
    data = {"id": "local-v1", "name": "Local plan", "amount_minor": 12000, "currency": "INR",
        "interval": "monthly", "total_cycles": 12, "whatsapp_numbers": 2}
    assert client.post("/api/platform/plans", headers=account["headers"], json=data).status_code == 200
    assert client.post("/api/platform/plans", headers=account["headers"], json=data).status_code == 409
    assert db_session.get(SubscriptionPlan, "local-v1").entitlements == {"whatsapp_numbers": 2}
    assert client.post("/api/platform/plans", headers=account["headers"], json={**data, "id": "invalid", "amount_minor": True}).status_code == 422


def test_removed_payment_routes_are_absent(client):
    paths = client.get("/openapi.json").json()["paths"]
    for path in ["/api/saas/checkout", "/api/saas/subscription/reconcile", "/api/saas/subscription/cancel",
                 "/api/saas/payment-gateway", "/api/platform/payment-gateway", "/api/webhooks/razorpay"]:
        assert path not in paths


def test_audit_failure_rolls_back_assignment(client, account, db_session, plan, monkeypatch):
    from app.services import manual_subscriptions
    grant(db_session, account)
    def fail_audit(*args, **kwargs):
        raise HTTPException(503, "Audit unavailable")
    monkeypatch.setattr(manual_subscriptions, "audit", fail_audit)
    assert client.post(url(account, "assign"), headers=account["headers"], json=assignment(plan)).status_code == 503
    db_session.expire_all()
    assert db_session.scalar(select(Subscription)) is None


def test_reassignment_preserves_identity_and_invoice_history(client, account, db_session, paid):
    grant(db_session, account)
    original_id = paid.id
    invoice = Invoice(tenant_id=paid.tenant_id, organization_id=paid.organization_id,
        payment_reference="old-payment", invoice_reference="old-invoice", amount_minor=12000,
        currency="INR", status="paid", buyer_snapshot={"legal_name": "Original buyer"})
    replacement = SubscriptionPlan(id="replacement", name="Replacement", amount_minor=24000,
        currency="INR", interval="monthly", total_cycles=12, entitlements={"whatsapp_numbers": 3})
    paid.status, paid.cancel_at_period_end = "cancelled", True
    db_session.add_all([invoice, replacement])
    db_session.commit()
    response = client.post(url(account, "assign"), headers=account["headers"], json=assignment(replacement))
    assert response.status_code == 200, response.text
    db_session.refresh(paid)
    assert paid.id == original_id and paid.plan_id == replacement.id
    assert paid.status == "active" and not paid.cancel_at_period_end
    assert billing.number_limit(db_session, user_for(account)) == 3
    db_session.refresh(invoice)
    assert invoice.payment_reference == "old-payment" and invoice.amount_minor == 12000
    assert invoice.buyer_snapshot == {"legal_name": "Original buyer"}


def test_inactive_plan_and_past_assignment_fail_without_mutation(client, account, db_session, plan):
    grant(db_session, account)
    plan.is_active = False
    db_session.commit()
    assert client.post(url(account, "assign"), headers=account["headers"], json=assignment(plan)).status_code == 404
    plan.is_active = True
    db_session.commit()
    now = datetime.now(UTC)
    data = assignment(plan, current_start=(now - timedelta(days=2)).isoformat(), current_end=(now - timedelta(days=1)).isoformat())
    assert client.post(url(account, "assign"), headers=account["headers"], json=data).status_code == 422
    assert db_session.scalar(select(Subscription)) is None


def test_renewal_clears_period_end_cancellation_but_cannot_reactivate_cancelled(client, account, db_session, paid):
    grant(db_session, account)
    paid.cancel_at_period_end = True
    db_session.commit()
    data = {"request_id": str(uuid4()), "reason": "Renewal approved", "days": 30}
    assert client.post(url(account, "renew"), headers=account["headers"], json=data).status_code == 200
    db_session.refresh(paid)
    assert not paid.cancel_at_period_end
    paid.status = "cancelled"
    db_session.commit()
    assert client.post(url(account, "renew"), headers=account["headers"], json={**data, "request_id": str(uuid4())}).status_code == 409


def test_another_staff_actor_cannot_reuse_an_operation_id(client, account, account_factory, db_session, plan):
    other = account_factory()
    grant(db_session, account)
    grant(db_session, other)
    data = assignment(plan)
    assert client.post(url(account, "assign"), headers=account["headers"], json=data).status_code == 200
    assert client.post(url(account, "assign"), headers=other["headers"], json=data).status_code == 409


def test_suspended_business_cannot_be_assigned_or_renewed(client, account, account_factory, db_session, plan):
    from app.models import Tenant
    target = account_factory()
    grant(db_session, account)
    assert client.post(url(target, "assign"), headers=account["headers"], json=assignment(plan)).status_code == 200
    tenant = db_session.get(Tenant, target["user"]["tenantId"])
    tenant.is_active = False
    db_session.commit()
    assert client.post(url(target, "assign"), headers=account["headers"], json=assignment(plan)).status_code == 409
    assert client.post(url(target, "renew"), headers=account["headers"], json={"request_id": str(uuid4()), "reason": "Approved", "days": 30}).status_code == 409
