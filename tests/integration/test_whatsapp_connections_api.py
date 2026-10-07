import hashlib
import hmac
import io
import json

import pytest
from cryptography.fernet import Fernet

from app.config.settings import get_settings
from app.routers import whatsapp_connections as router
from app.models import WhatsAppConnection, WhatsAppBulkJob
from app.services import meta_whatsapp
from app.services.whatsapp_connections import encrypt_token

pytestmark = pytest.mark.integration


@pytest.fixture
def meta_setup(monkeypatch):
    config = get_settings()
    monkeypatch.setattr(config, 'meta_app_id', '111')
    monkeypatch.setattr(config, 'whatsapp_signup_config_id', '222')
    monkeypatch.setattr(config, 'meta_app_secret', 'private-test-secret')
    monkeypatch.setattr(config, 'whatsapp_token_encryption_key', Fernet.generate_key().decode())
    assets = [{'waba_id': '444', 'phone_number_id': '333', 'display_phone_number': '+919000000000', 'verified_name': 'Business'}]
    monkeypatch.setattr(router, 'authorized_assets', lambda token: (assets, None))
    monkeypatch.setattr(router, 'graph', lambda path, *args, **kwargs: {'access_token': 'tenant-token'} if path == 'oauth/access_token' else {'success': True})
    return assets


def prepare(client, account):
    start = client.post('/api/whatsapp-connection/start', headers=account['headers'])
    assert start.status_code == 200, start.text
    state = start.json()['data']['state']
    exchange = client.post('/api/whatsapp-connection/exchange', headers=account['headers'], json={'state': state, 'code': 'one-use-code'})
    assert exchange.status_code == 200, exchange.text
    assert 'tenant-token' not in exchange.text
    return state


def test_connection_flow_is_private_and_sends_use_tenant_credentials(client, account, meta_setup, monkeypatch, db_session):
    state = prepare(client, account)
    selected = client.post('/api/whatsapp-connection/select', headers=account['headers'], json={'state': state, 'waba_id': '444', 'phone_number_id': '333'})
    assert selected.status_code == 200, selected.text
    assert selected.json()['data']['connected'] is True
    assert 'tenant-token' not in selected.text
    row = db_session.query(WhatsAppConnection).filter_by(organization_id=account['user']['organization_id']).one()
    assert row.encrypted_access_token != 'tenant-token'
    def provider(request, timeout):
        assert '/333/messages' in request.full_url
        assert request.get_header('Authorization') == 'Bearer tenant-token'
        return io.BytesIO(b'{"messages":[{"id":"wamid.private"}]}')
    monkeypatch.setattr(meta_whatsapp, 'urlopen', provider)
    sent = client.post('/api/communications/whatsapp', headers=account['headers'], json={'phone': '9000000000', 'message': 'Hello'})
    assert sent.status_code == 200, sent.text
    assert sent.json()['data']['status'] == 'accepted'
    assert client.delete('/api/whatsapp-connection/', headers=account['headers']).status_code == 200
    assert client.post('/api/communications/whatsapp', headers=account['headers'], json={'phone': '9000000000', 'message': 'Hello'}).status_code == 409


def test_other_tenant_cannot_reuse_attempt_or_claim_connected_sender(client, account, account_factory, meta_setup):
    other = account_factory()
    state = prepare(client, account)
    response = client.post('/api/whatsapp-connection/select', headers=other['headers'], json={'state': state, 'waba_id': '444', 'phone_number_id': '333'})
    assert response.status_code == 400
    own = client.post('/api/whatsapp-connection/select', headers=account['headers'], json={'state': state, 'waba_id': '444', 'phone_number_id': '333'})
    assert own.status_code == 200
    assert client.get('/api/whatsapp-connection/', headers=other['headers']).json()['data']['connected'] is False
    other_state = prepare(client, other)
    conflict = client.post('/api/whatsapp-connection/select', headers=other['headers'], json={'state': other_state, 'waba_id': '444', 'phone_number_id': '333'})
    assert conflict.status_code == 409


def test_code_cannot_be_replayed_and_ungranted_phone_is_rejected(client, account, meta_setup):
    state = prepare(client, account)
    assert client.post('/api/whatsapp-connection/exchange', headers=account['headers'], json={'state': state, 'code': 'one-use-code'}).status_code == 400
    assert client.post('/api/whatsapp-connection/select', headers=account['headers'], json={'state': state, 'waba_id': '444', 'phone_number_id': '999'}).status_code == 403


def test_signed_status_updates_only_sender_organization(client, account, account_factory, meta_setup, db_session):
    other = account_factory()
    jobs = []
    for owner, sender, waba in [(account, '333', '444'), (other, '555', '666')]:
        tenant = owner['user']['tenant_id']; organization = owner['user']['organization_id']
        db_session.add(WhatsAppConnection(tenant_id=tenant, organization_id=organization, waba_id=waba, phone_number_id=sender,
            encrypted_access_token=encrypt_token('token-'+sender, tenant, organization), connected_by=owner['user']['id']))
        job = WhatsAppBulkJob(tenant_id=tenant, organization_id=organization, title='Test', message_template='Hello', audience_type='custom',
            audience_payload={'sender_phone_number_id': sender}, status='in_progress', recipients_summary=[{'message_id': 'same-id', 'status': 'accepted'}])
        db_session.add(job); jobs.append(job)
    db_session.commit()
    body = json.dumps({'object': 'whatsapp_business_account', 'entry': [{'id': '444', 'changes': [{'value': {
        'metadata': {'phone_number_id': '333'}, 'statuses': [{'id': 'same-id', 'status': 'delivered', 'timestamp': '1791283200'}],
    }}]}]}).encode()
    signature = 'sha256=' + hmac.new(b'private-test-secret', body, hashlib.sha256).hexdigest()
    response = client.post('/api/webhooks/whatsapp', content=body, headers={'x-hub-signature-256': signature})
    assert response.status_code == 200, response.text
    for job in jobs: db_session.refresh(job)
    assert jobs[0].recipients_summary[0]['status'] == 'delivered'
    assert jobs[1].recipients_summary[0]['status'] == 'accepted'
