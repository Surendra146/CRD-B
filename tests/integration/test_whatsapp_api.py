"""Real PostgreSQL JSONB persistence for dispatch and signed status updates."""
import hashlib
import hmac
import json

import pytest

from app.config.settings import get_settings
from app.routers import communications

pytestmark = pytest.mark.integration


def test_dispatch_then_webhook_updates_persisted_job(client, account, monkeypatch, db_session):
    settings = get_settings()
    monkeypatch.setattr(settings, "meta_app_secret", "test-app-secret")
    from cryptography.fernet import Fernet
    from app.models import WhatsAppConnection
    from app.services.whatsapp_connections import encrypt_token
    monkeypatch.setattr(settings, "whatsapp_token_encryption_key", Fernet.generate_key().decode())
    tenant_id = account["user"]["tenant_id"]
    org_id = account["user"]["organization_id"]
    db_session.add(WhatsAppConnection(tenant_id=tenant_id, organization_id=org_id, waba_id="999", phone_number_id="123", encrypted_access_token=encrypt_token("test-token", tenant_id, org_id), connected_by=account["user"]["id"]))
    db_session.commit()

    monkeypatch.setattr(communications, "send_message", lambda *args, **kwargs: {
        "message_id": "wamid.integration", "status": "accepted", "phone": "919000000000",
    })
    sent = client.post("/api/communications/whatsapp/bulk", headers=account["headers"], json={
        "audience_type": "custom_numbers", "audience": {"numbers": ["9000000000"]}, "message": "Hello",
    })
    assert sent.status_code == 200, sent.text
    job = sent.json()["data"]
    job_id = job.get("id") or job["_id"]
    assert job["recipients_summary"][0]["status"] == "accepted"
    body = json.dumps({"object": "whatsapp_business_account", "entry": [{"id": "999", "changes": [{"value": {
        "metadata": {"phone_number_id": "123"},
        "statuses": [{"id": "wamid.integration", "status": "delivered", "timestamp": "1791283200"}],
    }}]}]}).encode()
    signature = "sha256=" + hmac.new(b"test-app-secret", body, hashlib.sha256).hexdigest()
    received = client.post("/api/webhooks/whatsapp", content=body, headers={"x-hub-signature-256": signature})
    assert received.status_code == 200, received.text
    updated = client.get(f"/api/communications/whatsapp/bulk/{job_id}", headers=account["headers"]).json()["data"]
    assert updated["recipients_summary"][0]["status"] == "delivered"
    assert updated["stats"]["delivered"] == 1
    assert updated["stats"]["pending"] == 0
    assert updated["status"] == "completed"


def test_scheduled_send_rejects_past_time(client, account):
    response = client.post("/api/communications/whatsapp/bulk", headers=account["headers"], json={
        "audience_type": "custom_numbers", "audience": {"numbers": ["9000000000"]},
        "message": "Hello", "scheduled_at": "2000-01-01T00:00:00Z",
    })
    assert response.status_code == 400
    assert "future" in response.json()["detail"]


def test_scheduled_job_waits_then_dispatches_once(client, account, monkeypatch, db_session, session_factory):
    from datetime import datetime, timezone, timedelta
    from cryptography.fernet import Fernet
    from app.models import WhatsAppConnection, WhatsAppBulkJob
    from app.services.whatsapp_connections import encrypt_token
    from app.services.whatsapp_scheduler import dispatch_due_job
    settings = get_settings()
    monkeypatch.setattr(settings, "whatsapp_token_encryption_key", Fernet.generate_key().decode())
    tenant_id = account["user"]["tenant_id"]
    org_id = account["user"]["organization_id"]
    db_session.add(WhatsAppConnection(tenant_id=tenant_id, organization_id=org_id, waba_id="999", phone_number_id="123", encrypted_access_token=encrypt_token("test-token", tenant_id, org_id), connected_by=account["user"]["id"]))
    db_session.commit()
    calls = []
    def send(*args, **kwargs):
        calls.append(kwargs.get("template"))
        return {"message_id": "wamid.scheduled", "status": "accepted", "phone": "919000000000"}
    monkeypatch.setattr(communications, "send_message", send)
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    response = client.post("/api/communications/whatsapp/bulk", headers=account["headers"], json={
        "audience_type": "custom_numbers", "audience": {"numbers": ["9000000000"]},
        "template": {"name": "hello_world", "language": {"code": "en_US"}}, "scheduled_at": future.isoformat(),
    })
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "scheduled"
    assert data["stats"]["sent"] == 0
    assert calls == []
    assert dispatch_due_job(session_factory) is False
    job = db_session.get(WhatsAppBulkJob, data.get("id") or data["_id"])
    job.scheduled_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
    db_session.commit()
    assert dispatch_due_job(session_factory) is True
    assert dispatch_due_job(session_factory) is False
    assert calls == [{"name": "hello_world", "language": {"code": "en_US"}}]
    db_session.refresh(job)
    assert job.recipients_summary[0]["status"] == "accepted"
