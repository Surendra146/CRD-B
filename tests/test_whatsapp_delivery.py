import hashlib
import hmac
import io
import json
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.services import meta_whatsapp as meta
from app.routers import webhooks, communications
from app.database.connection import get_db
from app.schemas.communication import CommunicationRequest
from app.schemas.whatsapp_marketing import WhatsAppBulkSendRequest


@pytest.fixture
def settings(monkeypatch):
    settings = SimpleNamespace(whatsapp_provider="meta_cloud", whatsapp_phone_number_id="123", whatsapp_access_token="private-token", whatsapp_graph_version="v23.0", meta_app_secret="test-app-secret")
    monkeypatch.setattr(meta, "get_settings", lambda: settings)
    monkeypatch.setattr(webhooks, "get_settings", lambda: settings)
    return settings


@pytest.mark.parametrize("phone,expected", [("8341645455", "918341645455"), ("+91 83416 45455", "918341645455"), ("0014155550123", "14155550123")])
def test_recipient_country_code(phone, expected):
    assert meta.normalize_phone(phone) == expected


def test_single_send_really_calls_meta_and_does_not_claim_delivery(settings, monkeypatch):
    def provider(request, timeout):
        payload = json.loads(request.data)
        assert request.full_url == "https://graph.facebook.com/v23.0/123/messages"
        assert request.get_header("Authorization") == "Bearer private-token"
        assert payload["to"] == "918341645455"
        assert payload["text"]["body"] == "Hello"
        return io.StringIO('{"messages":[{"id":"wamid.test"}]}')
    monkeypatch.setattr(meta, "urlopen", provider)
    result = communications.send_whatsapp(CommunicationRequest(phone="8341645455", message="Hello"))
    assert result["data"]["message_id"] == "wamid.test"
    assert result["data"]["status"] == "accepted"
    assert "not yet confirmed" in result["message"]


def test_meta_rejection_is_not_success_and_token_is_redacted(settings, monkeypatch):
    def provider(*args, **kwargs):
        raise HTTPError("https://graph.facebook.com", 400, "Bad Request", {}, io.BytesIO(b'{"error":{"code":190,"message":"invalid private-token"}}'))
    monkeypatch.setattr(meta, "urlopen", provider)
    with pytest.raises(HTTPException) as error:
        meta.send_message("8341645455", "Hello")
    assert error.value.status_code == 502
    assert error.value.detail["code"] == 190
    assert "private-token" not in str(error.value.detail)


def test_missing_configuration_never_reports_success(settings):
    settings.whatsapp_access_token = ""
    with pytest.raises(HTTPException) as error:
        meta.send_message("8341645455", "Hello")
    assert error.value.status_code == 503


def test_no_silent_ignoring_of_attachments():
    with pytest.raises(HTTPException):
        meta.build_message("8341645455", "Hello", media_files=[{"url": "blob:local"}])


def test_template_uses_meta_template_type():
    template = {"name": "hello_world", "language": {"code": "en_US"}}
    payload = meta.build_message("8341645455", "", template=template)
    assert payload["type"] == "template"
    assert payload["template"] == template


def test_delivery_does_not_regress():
    delivered = meta.apply_status({"status": "accepted"}, {"status": "delivered", "timestamp": "100"})
    assert delivered["delivered_at"]
    assert meta.apply_status(delivered, {"status": "sent", "timestamp": "110"}) == delivered
    assert meta.apply_status(delivered, {"status": "failed", "timestamp": "90"}) == delivered


def test_bulk_dispatch_records_provider_acceptance_and_failure(settings, monkeypatch):
    class DB:
        def add(self, job):
            self.job = job
        def commit(self): pass
        def refresh(self, job, **kwargs): pass
    db = DB()
    monkeypatch.setattr(communications, "model_to_dict", lambda job: {"stats": job.stats, "recipients_summary": job.recipients_summary})
    def provider(phone, message, **kwargs):
        if phone == "9000000001":
            raise HTTPException(502, {"code": 131030, "message": "Recipient not allowed"})
        return {"status": "accepted", "message_id": "wamid.bulk", "phone": meta.normalize_phone(phone)}
    monkeypatch.setattr(communications, "send_message", provider)
    user = SimpleNamespace(tenant_id=1, organization_id=2, tenant_code="test", id=3)
    request = WhatsAppBulkSendRequest(audience_type="custom_numbers", audience={"numbers": ["9000000000", "9000000001"]}, message="Hello")
    result = communications.send_bulk_whatsapp(request, user, db)
    assert result["data"]["stats"] == {"total": 2, "sent": 1, "delivered": 0, "failed": 1, "pending": 1}
    assert [r["status"] for r in db.job.recipients_summary] == ["accepted", "failed"]
    assert all(r["delivered_at"] is None for r in db.job.recipients_summary)


def test_signed_webhook_is_registered_and_updates_actual_delivery(settings):
    job = SimpleNamespace(recipients_summary=[{"message_id": "wamid.test", "status": "accepted"}], stats={}, status="in_progress")
    class DB:
        def scalars(self, query): return self
        def all(self): return [job]
        def commit(self): pass
    app = FastAPI()
    app.include_router(webhooks.router, prefix="/api/webhooks")
    app.dependency_overrides[get_db] = lambda: DB()
    body = json.dumps({"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "123"}, "statuses": [{"id": "wamid.test", "status": "failed", "timestamp": "123", "errors": [{"code": 131047, "message": "Outside service window"}]}]}}]}]}).encode()
    signature = "sha256=" + hmac.new(settings.meta_app_secret.encode(), body, hashlib.sha256).hexdigest()
    with TestClient(app) as client:
        assert client.post("/api/webhooks/whatsapp", content=body).status_code == 403
        assert job.recipients_summary[0]["status"] == "accepted"
        response = client.post("/api/webhooks/whatsapp", content=body, headers={"x-hub-signature-256": signature})
    assert response.status_code == 200
    assert job.recipients_summary[0]["status"] == "failed"
    assert job.recipients_summary[0]["error"][0]["code"] == 131047
    assert job.stats["failed"] == 1
