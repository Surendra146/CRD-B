"""Real PostgreSQL JSONB persistence for dispatch and signed status updates."""
import hashlib
import hmac
import json

import pytest

from app.config.settings import get_settings
from app.routers import communications

pytestmark = pytest.mark.integration


def test_dispatch_then_webhook_updates_persisted_job(client, account, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "whatsapp_phone_number_id", "sender-123")
    monkeypatch.setattr(settings, "whatsapp_access_token", "test-token")
    monkeypatch.setattr(settings, "meta_app_secret", "test-app-secret")
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
    body = json.dumps({"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {
        "metadata": {"phone_number_id": "sender-123"},
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


def test_scheduled_send_never_claims_delivery(client, account):
    response = client.post("/api/communications/whatsapp/bulk", headers=account["headers"], json={
        "audience_type": "custom_numbers", "audience": {"numbers": ["9000000000"]},
        "message": "Hello", "scheduled_at": "2030-01-01T00:00:00Z",
    })
    assert response.status_code == 400
    assert "not implemented" in response.json()["detail"]
