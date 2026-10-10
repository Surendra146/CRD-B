from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.config.settings import get_settings
from app.models import Campaign, Customer, WhatsAppBulkJob, WhatsAppTemplate
from app.models.saas import CampaignOutbox
from app.services.consent import assert_send_allowed, set_consent

pytestmark = pytest.mark.integration


def test_template_approval_is_scoped_to_tenant_and_waba(account, account_factory, db_session, monkeypatch):
    monkeypatch.setattr(get_settings(), 'enforce_whatsapp_consent', True)
    other = account_factory()
    tenant, org = account['user']['tenantId'], account['user']['organizationId']
    set_consent(db_session, tenant, org, '9000000000', True, 'form', 'signed evidence')
    template = WhatsAppTemplate(tenant_id=other['user']['tenantId'], organization_id=other['user']['organizationId'],
        name='hello', category='MARKETING', whatsapp_template_name='hello', content={'language': 'en'},
        targeting={'waba_id': '444'}, stats={'meta_status': 'APPROVED'}, is_active=True)
    db_session.add(template)
    db_session.commit()
    payload = {'name': 'hello', 'language': {'code': 'en'}}
    with pytest.raises(HTTPException, match='approved template'):
        assert_send_allowed(db_session, tenant, org, '9000000000', payload, '444')
    db_session.add(WhatsAppTemplate(tenant_id=tenant, organization_id=org, name='hello', category='MARKETING',
        whatsapp_template_name='hello', content={'language': 'en'}, targeting={'waba_id': '444'},
        stats={'meta_status': 'APPROVED'}, is_active=True))
    db_session.commit()
    assert_send_allowed(db_session, tenant, org, '9000000000', payload, '444')
    with pytest.raises(HTTPException, match='approved template'):
        assert_send_allowed(db_session, tenant, org, '9000000000', payload, 'different-waba')


def test_campaign_launch_queues_once_and_pause_resume_preserve_outbox(client, account, db_session, monkeypatch):
    from app.routers import communications
    monkeypatch.setattr(get_settings(), 'campaign_transport', 'celery')
    monkeypatch.setattr(communications, 'resolve_credentials', lambda *args: SimpleNamespace(
        whatsapp_phone_number_id='333', whatsapp_access_token='test-token', whatsapp_waba_id='444',
        whatsapp_graph_version='v25.0', whatsapp_provider='meta'))
    monkeypatch.setattr(communications, 'require_configuration', lambda *args: None)
    tenant, org = account['user']['tenantId'], account['user']['organizationId']
    template = WhatsAppTemplate(tenant_id=tenant, organization_id=org, name='hello', category='MARKETING',
        whatsapp_template_name='hello', content={'language': 'en'}, targeting={'waba_id': '444'},
        stats={'meta_status': 'APPROVED'}, is_active=True)
    db_session.add(template)
    db_session.flush()
    campaign = Campaign(tenant_id=tenant, organization_id=org, name='Campaign', type='one_time',
        template_id=template.id, audience={'type': 'all'}, status='draft', created_by=account['user']['id'])
    db_session.add_all([campaign, Customer(tenant_id=tenant, organization_id=org, name='Customer', phone='9000000000')])
    db_session.commit()
    url = f'/api/campaigns/{campaign.id}'
    response = client.post(url + '/launch', headers=account['headers'])
    assert response.status_code == 200, response.text
    job_id = response.json()['data']['id']
    assert client.post(url + '/launch', headers=account['headers']).status_code == 409
    assert client.post(url + '/pause', headers=account['headers']).status_code == 200
    db_session.expire_all()
    assert db_session.get(WhatsAppBulkJob, job_id).status == 'paused'
    assert client.post(url + '/resume', headers=account['headers']).status_code == 200
    db_session.expire_all()
    assert db_session.get(WhatsAppBulkJob, job_id).status == 'scheduled'
    assert db_session.scalar(select(CampaignOutbox).where(CampaignOutbox.bulk_job_id == job_id)).status == 'pending'


def test_platform_permissions_are_returned_only_for_explicit_staff(client, account, db_session):
    from app.models.saas import PlatformStaff
    assert client.get('/api/auth/me', headers=account['headers']).json()['data']['platformPermissions'] == []
    db_session.add(PlatformStaff(user_id=account['user']['id'], permissions=['tenants.read']))
    db_session.commit()
    assert client.get('/api/auth/me', headers=account['headers']).json()['data']['platformPermissions'] == ['tenants.read']


def test_template_editor_cannot_forge_or_modify_meta_approval(client, account, db_session):
    payload = {"name": "forged", "category": "MARKETING", "targeting": {"waba_id": "444", "meta_id": "123"}, "stats": {"meta_status": "APPROVED"}}
    assert client.post('/api/templates/', headers=account['headers'], json=payload).status_code == 422
    row = WhatsAppTemplate(tenant_id=account['user']['tenantId'], organization_id=account['user']['organizationId'],
        name='synced', category='MARKETING', targeting={'meta_id': '123', 'waba_id': '444'}, stats={'meta_status': 'APPROVED'})
    db_session.add(row)
    db_session.commit()
    assert client.put(f'/api/templates/{row.id}', headers=account['headers'], json={'content': {'language': 'different'}}).status_code == 409
