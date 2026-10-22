"""Tenant-scoped API -> provider -> synchronization -> queued media sending."""
import copy
import io
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from PIL import Image
from sqlalchemy import select

from app.models import WhatsAppConnection, WhatsAppTemplate, WhatsAppBulkJob, User
from app.config.settings import get_settings
from app.services.template_definitions import compile_draft

pytestmark = pytest.mark.integration


def credentials():
    return SimpleNamespace(whatsapp_provider='meta_cloud', whatsapp_phone_number_id='333',
        whatsapp_waba_id='444', whatsapp_access_token='never-log-this', whatsapp_graph_version='v23.0')


def image_bytes():
    f = io.BytesIO(); Image.new('RGB', (8, 8)).save(f, 'PNG'); return f.getvalue()


def content():
    return {'meta_name': 'greeting', 'language': 'en_US', 'header': {'type': 'NONE'}, 'body': 'Hi {{name}}, welcome.',
            'mappings': {'body': {'name': 'customer.name'}}, 'examples': {'body': {'name': 'Alice'}}, 'buttons': []}


def new_template(client, account):
    result = client.post('/api/templates/', headers=account['headers'], json={'name': 'Greeting', 'category': 'MARKETING', 'content': content()})
    assert result.status_code == 200, result.text
    return result.json()['data']['id']


def test_submit_refresh_edit_and_per_recipient_send(client, account, db_session, monkeypatch):
    from app.services import template_workflow as workflow
    from app.routers import communications
    monkeypatch.setattr(workflow, 'resolve_credentials', lambda *a: credentials())
    monkeypatch.setattr(communications, 'resolve_marketing_credentials', lambda *a: credentials())
    calls = []
    monkeypatch.setattr(communications, 'send_message', lambda phone, text, **kw: calls.append(kw['template']) or {'message_id': f'wamid.{phone}', 'status': 'accepted', 'phone': phone})
    meta = {'id': '123', 'status': 'PENDING'}
    monkeypatch.setattr(workflow, 'graph', lambda *a, **kw: copy.deepcopy(meta))
    identifier = new_template(client, account)
    response = client.post(f'/api/templates/{identifier}/submit', headers=account['headers'])
    assert response.status_code == 200, response.text
    assert client.post(f'/api/templates/{identifier}/submit', headers=account['headers']).status_code == 409
    assert client.post('/api/communications/whatsapp', headers=account['headers'], json={'phone': '9000000000', 'template': {'id': identifier}, 'recipient': {'name': 'Bob'}}).status_code == 409
    submitted = response.json()['data']['workflow']['submitted']
    meta.update(**{k: submitted[k] for k in ('name', 'language', 'category', 'components')}, status='APPROVED')
    assert client.post(f'/api/templates/{identifier}/refresh', headers=account['headers']).status_code == 200
    changed = content(); changed['body'] = 'Changed unpublished content.'
    assert client.put(f'/api/templates/{identifier}', headers=account['headers'], json={'content': changed}).status_code == 200
    response = client.post('/api/communications/whatsapp/bulk', headers=account['headers'], json={
        'audience_type': 'custom_numbers', 'audience': {'numbers': [{'phone': '9000000000', 'name': 'Bob'}, {'phone': '9000000001', 'name': 'Carol'}]},
        'template': {'id': identifier, 'components': [{'type': 'body', 'parameters': [{'type': 'text', 'text': 'ATTACK'}]}]}, 'batch_delay_seconds': 0})
    assert response.status_code == 200, response.text
    assert [c['components'][0]['parameters'][0]['text'] for c in calls] == ['Bob', 'Carol']
    assert all(c['name'] == 'greeting' and c['language'] == {'code': 'en_US'} for c in calls)
    assert response.json()['data']['recipients_summary'][0]['personalized_message'] == 'Hi Bob, welcome.'
    db_session.expire_all()
    row = db_session.get(WhatsAppTemplate, identifier)
    assert row.content['body'] == changed['body']
    assert row.workflow['approved']['components'][0]['text'] == 'Hi {{1}}, welcome.'


def test_media_routes_isolate_orgs_and_validate_contents(client, account, account_factory, monkeypatch, tmp_path):
    monkeypatch.setenv('WHATSAPP_TEMPLATE_MEDIA_ROOT', str(tmp_path))
    identifier = new_template(client, account)
    other = account_factory()
    endpoint = f'/api/templates/{identifier}/media'
    bad = client.post(endpoint, headers=account['headers'], files={'file': ('fake.png', b'bad', 'image/png')})
    assert bad.status_code == 422
    uploaded = client.post(endpoint, headers=account['headers'], files={'file': ('real.png', image_bytes(), 'image/png')})
    assert uploaded.status_code == 200, uploaded.text
    asset_id = uploaded.json()['data']['id']
    assert client.get(f'{endpoint}/{asset_id}', headers=account['headers']).content == image_bytes()
    assert client.get(f'{endpoint}/{asset_id}', headers=other['headers']).status_code == 404
    assert client.post(endpoint, headers=other['headers'], files={'file': ('real.png', image_bytes(), 'image/png')}).status_code == 404
    for action in ['submit', 'refresh']:
        assert client.post(f'/api/templates/{identifier}/{action}', headers=other['headers']).status_code == 404


def test_queued_media_retains_version_and_reuploads_at_dispatch(client, account, db_session, monkeypatch, tmp_path):
    from app.routers import communications
    from app.services import template_workflow as workflow
    monkeypatch.setenv('WHATSAPP_TEMPLATE_MEDIA_ROOT', str(tmp_path))
    monkeypatch.setattr(communications, 'resolve_marketing_credentials', lambda *a: credentials())
    identifier = new_template(client, account)
    uploaded = client.post(f'/api/templates/{identifier}/media', headers=account['headers'], files={'file': ('real.png', image_bytes(), 'image/png')})
    asset_id = uploaded.json()['data']['id']
    row = db_session.get(WhatsAppTemplate, identifier)
    c = content(); c['header'] = {'type': 'IMAGE', 'asset_id': asset_id}
    d = compile_draft('greeting', 'MARKETING', c); d.update(meta_id='123', waba_id='444')
    row.workflow = {**row.workflow, 'approved': d}; row.targeting = {'waba_id': '444', 'meta_id': '123'}
    row.stats = {'meta_status': 'APPROVED'}; row.is_active = True
    db_session.commit()
    response = client.post('/api/communications/whatsapp/bulk', headers=account['headers'], json={
        'audience_type': 'custom_numbers', 'audience': {'numbers': [{'phone': '9000000000', 'name': 'Bob'}]},
        'template': {'id': identifier, 'media_asset_id': asset_id}, 'scheduled_at': (datetime.now(UTC) + timedelta(hours=1)).isoformat()})
    assert response.status_code == 200, response.text
    job = db_session.get(WhatsAppBulkJob, response.json()['data']['id'])
    assert job.audience_payload['template_snapshot']['definition']['meta_id'] == '123'
    row.content = {'body': 'Unpublished edits'}; db_session.commit()
    uploads, sends = [], []
    monkeypatch.setattr(workflow, 'sending_media', lambda *a: uploads.append(a[1]) or '999')
    monkeypatch.setattr(communications, 'send_message', lambda *a, **kw: sends.append(kw['template']) or {'message_id': 'wamid.media', 'status': 'accepted'})
    communications.dispatch_bulk_job(db_session, job, credentials())
    assert uploads == [asset_id]
    assert sends[0]['components'][0] == {'type': 'header', 'parameters': [{'type': 'image', 'image': {'id': '999'}}]}
    assert sends[0]['components'][1]['parameters'] == [{'type': 'text', 'text': 'Bob'}]
    communications.dispatch_bulk_job(db_session, job, credentials())
    assert len(sends) == 1


def test_sync_merges_by_submission_identity_without_losing_draft(client, account, db_session, monkeypatch):
    from app.routers import managed_whatsapp
    identifier = new_template(client, account)
    row = db_session.get(WhatsAppTemplate, identifier)
    d = compile_draft('greeting', 'MARKETING', content()); d.update(meta_id='123', waba_id='444')
    row.workflow = {'submitted': d, 'status': 'PENDING'}
    before = copy.deepcopy(row.content)
    db_session.add(WhatsAppConnection(tenant_id=account['user']['tenant_id'], organization_id=account['user']['organization_id'],
        waba_id='444', phone_number_id='333', encrypted_access_token='encrypted', connected_by=account['user']['id']))
    db_session.commit()
    monkeypatch.setattr(managed_whatsapp, 'decrypt_token', lambda *a: 'secret')
    monkeypatch.setattr(managed_whatsapp, 'graph', lambda *a, **kw: {'data': [{**d, 'id': '123', 'status': 'APPROVED'}]})
    for _ in range(2):
        response = client.post('/api/saas/templates/sync', headers=account['headers'])
        assert response.status_code == 200, response.text
    db_session.expire_all()
    rows = db_session.scalars(select(WhatsAppTemplate).where(WhatsAppTemplate.organization_id == account['user']['organization_id'])).all()
    assert len(rows) == 1 and rows[0].content == before
    assert rows[0].workflow['approved']['parameters'] == d['parameters']


def test_template_permission_blocks_mutations(client, account, db_session):
    identifier = new_template(client, account)
    user = db_session.get(User, account['user']['id'])
    user.allowed_modules = ['customers']
    user.role = 'staff'
    db_session.commit()
    assert client.post(f'/api/templates/{identifier}/submit', headers=account['headers']).status_code == 403
