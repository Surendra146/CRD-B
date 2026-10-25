"""Interlock tests never contact databases, brokers or provider services."""
import copy
import io
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config.settings import Settings, get_settings
from app.services import whatsapp_interlock as gate, meta_whatsapp as meta
from app.routers import communications


def configure(monkeypatch, enabled):
    monkeypatch.setenv('WHATSAPP_SENDING_ENABLED', 'true' if enabled else 'false')
    get_settings.cache_clear()


@pytest.mark.parametrize('value', [None, '', 'false', '0', 'yes', 'invalid', '1'])
def test_default_and_invalid_values_fail_closed(monkeypatch, value):
    if value is None:
        monkeypatch.delenv('WHATSAPP_SENDING_ENABLED', raising=False)
    else:
        monkeypatch.setenv('WHATSAPP_SENDING_ENABLED', value)
    assert Settings().whatsapp_sending_enabled is False


def test_explicit_true(monkeypatch):
    monkeypatch.setenv('WHATSAPP_SENDING_ENABLED', ' TRUE ')
    assert Settings().whatsapp_sending_enabled is True


def test_provider_boundary_disabled_and_enabled(monkeypatch):
    provider = Mock(return_value=io.StringIO('{"messages":[{"id":"mock-id"}]}'))
    monkeypatch.setattr(meta, 'urlopen', provider)
    credentials = NS(whatsapp_provider='meta_cloud', whatsapp_phone_number_id='123',
        whatsapp_access_token='test', whatsapp_graph_version='v23.0')
    configure(monkeypatch, False)
    with pytest.raises(gate.WhatsAppSendingDisabled):
        meta.send_message('9000000000', 'hello', connection=credentials)
    provider.assert_not_called()
    configure(monkeypatch, True)
    assert meta.send_message('9000000000', 'hello', connection=credentials)['status'] == 'accepted'
    provider.assert_called_once()


@pytest.mark.parametrize('route', ['/whatsapp', '/whatsapp/send', '/'])
def test_direct_routes_http_503_without_provider(monkeypatch, route):
    from app.services.security import require_whatsapp_access, require_organization
    from app.database.connection import get_db
    configure(monkeypatch, False)
    provider = Mock(); monkeypatch.setattr(communications, 'send_message', provider)
    db = Mock()
    app = FastAPI(); app.include_router(communications.router)
    app.dependency_overrides[require_whatsapp_access] = lambda: NS()
    app.dependency_overrides[require_organization] = lambda: NS()
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        response = client.post(route, json={'phone': '9000000000', 'message': 'hello'})
    assert response.status_code == 503
    provider.assert_not_called(); db.commit.assert_not_called()


def test_disabled_bulk_creation_does_not_persist_or_send(monkeypatch):
    configure(monkeypatch, False)
    db = Mock()
    with pytest.raises(gate.WhatsAppSendingDisabled):
        communications.send_bulk_whatsapp(Mock(), NS(), db)
    db.add.assert_not_called(); db.commit.assert_not_called()


def test_graph_only_blocks_message_posts(monkeypatch):
    from app.services import whatsapp_connections as connections
    configure(monkeypatch, False)
    provider = Mock(side_effect=lambda *a, **k: io.StringIO('{"data":[]}'))
    monkeypatch.setattr(connections, 'urlopen', provider)
    with pytest.raises(gate.WhatsAppSendingDisabled):
        connections.graph('123/messages', 'mock', method='POST', data={})
    provider.assert_not_called()
    connections.graph('123/message_templates', 'mock')
    connections.graph('123/media', 'mock', method='POST', data={})
    assert provider.call_count == 2


@pytest.mark.parametrize('task_name', ['publish_due', 'deliver_job'])
def test_disabled_celery_entry_does_not_claim_or_mutate(monkeypatch, task_name):
    from app import tasks
    from app.database import connection, authorization
    configure(monkeypatch, False)
    session = Mock(); claim = Mock()
    monkeypatch.setattr(connection, 'ControlSessionLocal', session)
    monkeypatch.setattr(connection, 'SessionLocal', session)
    monkeypatch.setattr(authorization, 'claim_campaign', claim)
    task = getattr(tasks, task_name)
    args = (1, 2, 3) if task_name == 'deliver_job' else ()
    task.run(*args)  # Direct function test only; no Celery consumer/broker.
    session.assert_not_called(); claim.assert_not_called()


def test_disabled_scheduler_preserves_pending_jobs(monkeypatch):
    from app.services.whatsapp_scheduler import dispatch_due_job
    configure(monkeypatch, False)
    factory = Mock()
    assert dispatch_due_job(factory) is False
    factory.assert_not_called()


def job():
    return NS(id=1, tenant_id=2, organization_id=3, created_by=4, batch_delay_seconds=0,
        status='in_progress', audience_payload={}, buttons=[], media_files=[], stats={},
        recipients_summary=[{'phone': '9000000000', 'personalized_message': 'hello', 'status': 'queued'},
                            {'phone': '9000000001', 'personalized_message': 'hello', 'status': 'unknown'},
                            {'phone': '9000000002', 'personalized_message': 'hello', 'status': 'delivered'}])


def test_pending_resume_after_process_restart_never_retries_unknown(monkeypatch):
    configure(monkeypatch, False)
    pending = job(); original = copy.deepcopy(pending.recipients_summary)
    db = Mock(spec=['refresh', 'commit'])
    provider = Mock(return_value={'status': 'accepted', 'message_id': 'mock'})
    monkeypatch.setattr(communications, 'send_message', provider)
    monkeypatch.setattr(communications, 'assert_send_allowed', Mock())
    monkeypatch.setattr(communications, 'model_to_dict', lambda row: {})
    with pytest.raises(gate.WhatsAppSendingDisabled):
        communications.dispatch_bulk_job(db, pending, NS())
    assert pending.recipients_summary == original
    db.commit.assert_not_called(); provider.assert_not_called()
    # New settings load models a coordinated process restart after authorization.
    configure(monkeypatch, True)
    communications.dispatch_bulk_job(db, pending, NS(whatsapp_waba_id='123'))
    assert [r['status'] for r in pending.recipients_summary] == ['accepted', 'unknown', 'delivered']
    provider.assert_called_once()
    communications.dispatch_bulk_job(db, pending, NS(whatsapp_waba_id='123'))
    provider.assert_called_once()


def test_pause_after_uncertainty_write_restores_only_unsent_recipient(monkeypatch):
    configure(monkeypatch, True)
    pending = job()
    db = Mock(spec=['refresh', 'commit'])
    monkeypatch.setattr(communications, 'assert_send_allowed', Mock())
    monkeypatch.setattr(communications, 'send_message', Mock(side_effect=gate.WhatsAppSendingDisabled()))
    with pytest.raises(gate.WhatsAppSendingDisabled):
        communications.dispatch_bulk_job(db, pending, NS(whatsapp_waba_id='123'))
    assert [r['status'] for r in pending.recipients_summary] == ['queued', 'unknown', 'delivered']


def test_enabled_scheduler_uses_existing_claim_path(monkeypatch):
    from app.services import whatsapp_scheduler
    from app.database import authorization
    from app import tasks
    factory = Mock()
    configure(monkeypatch, False)
    assert whatsapp_scheduler.dispatch_due_job(factory) is False
    configure(monkeypatch, True)
    monkeypatch.setattr(authorization, 'enabled', lambda: True)
    claim = {'job_id': 1, 'tenant_id': 2, 'organization_id': 3}
    monkeypatch.setattr(authorization, 'claim_campaign', Mock(return_value=claim))
    factory.return_value.__enter__ = Mock(return_value=Mock())
    factory.return_value.__exit__ = Mock(return_value=False)
    deliver = Mock(); monkeypatch.setattr(tasks.deliver_job, 'run', deliver)
    assert whatsapp_scheduler.dispatch_due_job(factory) is True
    deliver.assert_called_once_with(1, 2, 3, claim)


@pytest.mark.parametrize('paused_during_dispatch', [False, True])
def test_celery_restart_and_outbox_not_completed_when_paused(monkeypatch, paused_during_dispatch):
    from app import tasks
    from app.database import connection, authorization, tenancy
    from app.services import security, whatsapp_connections
    pending = job(); pending.status = 'scheduled'
    from datetime import datetime, timedelta
    pending.scheduled_at = datetime.now() - timedelta(days=1)
    pending.audience_payload = {'sender_phone_number_id': '123'}
    outbox = NS(status='published')
    db = Mock()
    db.scalar.side_effect = [pending, outbox]
    user = NS(id=4, tenant_id=2, organization_id=3, is_active=True)
    db.get.side_effect = [user, NS(is_active=True)]
    session = Mock(); session.return_value.__enter__ = Mock(return_value=db)
    session.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(connection, 'SessionLocal', session)
    monkeypatch.setattr(authorization, 'enabled', lambda: False)
    monkeypatch.setattr(tenancy, 'bind_scope', Mock())
    monkeypatch.setattr(security, 'require_whatsapp_access', Mock())
    monkeypatch.setattr(whatsapp_connections, 'resolve_marketing_credentials', lambda *a: NS(whatsapp_phone_number_id='123'))
    dispatch = Mock(side_effect=gate.WhatsAppSendingDisabled() if paused_during_dispatch else None)
    monkeypatch.setattr(communications, 'dispatch_bulk_job', dispatch)
    configure(monkeypatch, False)
    tasks.deliver_job.run(1, 2, 3)
    session.assert_not_called()
    assert pending.status == 'scheduled' and outbox.status == 'published'
    configure(monkeypatch, True)
    tasks.deliver_job.run(1, 2, 3)
    dispatch.assert_called_once()
    assert outbox.status == ('published' if paused_during_dispatch else 'completed')
    assert pending.recipients_summary[0]['status'] == 'queued'


def test_outbox_publication_resumes_only_enabled(monkeypatch):
    from app import tasks
    from app.database import connection, authorization
    session = Mock(); session.return_value.__enter__ = Mock(return_value=Mock())
    session.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(connection, 'ControlSessionLocal', session)
    monkeypatch.setattr(authorization, 'enabled', lambda: True)
    claim = {'job_id': 1, 'tenant_id': 2, 'organization_id': 3}
    claim_fn = Mock(side_effect=[claim, None])
    monkeypatch.setattr(authorization, 'claim_campaign', claim_fn)
    publish = Mock(); monkeypatch.setattr(tasks.celery_app, 'send_task', publish)
    configure(monkeypatch, False)
    tasks.publish_due.run()
    claim_fn.assert_not_called(); publish.assert_not_called()
    configure(monkeypatch, True)
    tasks.publish_due.run()
    publish.assert_called_once_with('hanuram.deliver_job', args=[1, 2, 3, claim])


def test_onboarding_test_message_blocked_without_changing_verification(monkeypatch):
    from datetime import datetime
    from app.services import onboarding
    from app.database import authorization
    configure(monkeypatch, False)
    row = NS(id='test', status='setup_in_progress', verification={}, tenant_id=2, organization_id=3)
    credentials = NS(id=1, updated_at=datetime.now(), phone_number_id='123')
    monkeypatch.setattr(onboarding, 'require_eligible', Mock())
    monkeypatch.setattr(onboarding, 'matching_connection', lambda *a: credentials)
    monkeypatch.setattr(onboarding, 'provider_checks', lambda *a: 'mock-token')
    monkeypatch.setattr(authorization, 'staff_scope', Mock())
    provider = Mock(); monkeypatch.setattr(onboarding, 'graph', provider)
    db = Mock(); db.scalar.return_value = NS(opted_in=True)
    with pytest.raises(gate.WhatsAppSendingDisabled):
        onboarding.verify(db, row, NS(), NS(test_phone='9000000000', template_name='test', language='en_US'))
    provider.assert_not_called(); db.add.assert_not_called()
    assert row.verification == {}
