from datetime import datetime, timezone, timedelta
import pytest
from fastapi import HTTPException
from app.services.whatsapp_scheduler import parse_schedule


def test_schedule_normalizes_offset_to_utc():
    future = datetime.now(timezone.utc) + timedelta(days=1)
    offset = timezone(timedelta(hours=5, minutes=30))
    assert parse_schedule(future.astimezone(offset).isoformat()) == future.replace(tzinfo=None)


@pytest.mark.parametrize("value", ["bad", "2000-01-01T00:00:00Z", "2099-01-01T00:00:00"])
def test_invalid_schedule_is_rejected(value):
    with pytest.raises(HTTPException) as error:
        parse_schedule(value)
    assert error.value.status_code == 400


def test_immediate_schedule():
    assert parse_schedule(None) is None


def test_scheduled_submission_does_not_call_meta(monkeypatch):
    from types import SimpleNamespace
    from app.routers import communications
    from app.schemas.whatsapp_marketing import WhatsAppBulkSendRequest
    connection = SimpleNamespace(whatsapp_phone_number_id="123")
    monkeypatch.setattr(communications, "resolve_credentials", lambda *args: connection)
    monkeypatch.setattr(communications, "require_configuration", lambda *args: None)
    monkeypatch.setattr(communications, "send_message", lambda *args, **kwargs: pytest.fail("Scheduled submission must not send"))
    monkeypatch.setattr(communications, "model_to_dict", lambda job: {"status": job.status, "stats": job.stats})
    class DB:
        def add(self, job): self.job = job
        def commit(self): pass
        def refresh(self, job): pass
    db = DB()
    future = datetime.now(timezone.utc) + timedelta(days=1)
    user = SimpleNamespace(tenant_id=1, organization_id=2, tenant_code="test", id=3)
    request = WhatsAppBulkSendRequest(audience_type="custom_numbers", audience={"numbers": ["9000000000"]}, message="Hello", scheduled_at=future.isoformat())
    result = communications.send_bulk_whatsapp(request, user, db)
    assert result["success"] is True
    assert result["data"]["status"] == "scheduled"
    assert result["data"]["stats"]["sent"] == 0
    assert db.job.scheduled_at == future.replace(tzinfo=None)


def test_worker_claims_job_before_dispatch_and_does_not_repeat(monkeypatch):
    from types import SimpleNamespace
    from app.routers import communications
    from app.services import whatsapp_scheduler, whatsapp_connections
    job = SimpleNamespace(status="scheduled", created_by=3, tenant_id=1, organization_id=2,
                          audience_payload={"sender_phone_number_id": "123"})
    user = SimpleNamespace(tenant_id=1, organization_id=2, is_active=True, role="owner")
    class DB:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def scalar(self, query): return job if job.status == "scheduled" else None
        def get(self, *args): return user
        def commit(self): self.committed = job.status
    db = DB()
    calls = []
    def dispatch(*args):
        assert db.committed == "in_progress"
        calls.append(job)
    monkeypatch.setattr(communications, "dispatch_bulk_job", dispatch)
    monkeypatch.setattr(whatsapp_connections, "resolve_credentials", lambda *args: SimpleNamespace(whatsapp_phone_number_id="123"))
    assert whatsapp_scheduler.dispatch_due_job(lambda: db) is True
    assert whatsapp_scheduler.dispatch_due_job(lambda: db) is False
    assert calls == [job]


def test_worker_does_not_send_when_sender_has_changed(monkeypatch):
    from types import SimpleNamespace
    from app.routers import communications
    from app.services import whatsapp_scheduler, whatsapp_connections
    job = SimpleNamespace(status="scheduled", created_by=3, tenant_id=1, organization_id=2,
                          audience_payload={"sender_phone_number_id": "123"}, recipients_summary=[{"status": "queued"}])
    user = SimpleNamespace(tenant_id=1, organization_id=2, is_active=True, role="owner")
    class DB:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def scalar(self, query): return job
        def get(self, *args): return user
        def commit(self): pass
        def rollback(self): pass
        def refresh(self, *args, **kwargs): pass
    monkeypatch.setattr(communications, "dispatch_bulk_job", lambda *args: pytest.fail("Changed sender must not dispatch"))
    monkeypatch.setattr(whatsapp_connections, "resolve_credentials", lambda *args: SimpleNamespace(whatsapp_phone_number_id="456"))
    assert whatsapp_scheduler.dispatch_due_job(DB) is True
    assert job.status == "failed"
    assert "sender has changed" in job.recipients_summary[0]["error"]
