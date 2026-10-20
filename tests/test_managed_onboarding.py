from datetime import UTC, datetime, timedelta
from types import SimpleNamespace as NS
from typing import Any, cast
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from app.services import onboarding as service
from app.routers.saas import OnboardingPayload, verification_completed
from app.routers.platform import OnboardingUpdate, VerificationPayload, staff_permission


def request(status='requested'):
    return NS(id='request', tenant_id=1, organization_id=2, phone='919000000000', status=status,
        history=[], verification={}, setup_started_at=None, assigned_admin_id=None,
        tenant_confirmed_at=None)


def subscription(status='active', start=-1, end=1):
    now = datetime.now(UTC)
    return NS(status=status, plan_id='plan', current_start=now + timedelta(days=start), current_end=now + timedelta(days=end))


@pytest.mark.parametrize('sub,entitlements,code', [
    (None, {'whatsapp_numbers': 1}, 'SUBSCRIPTION_NOT_FOUND'),
    (subscription(end=-1, start=-2), {'whatsapp_numbers': 1}, 'SUBSCRIPTION_EXPIRED'),
    (subscription(status='cancelled'), {'whatsapp_numbers': 1}, 'SUBSCRIPTION_NOT_ACTIVE'),
    (subscription(start=1, end=2), {'whatsapp_numbers': 1}, 'SUBSCRIPTION_NOT_ACTIVE'),
    (subscription(), {}, 'WHATSAPP_ENTITLEMENT_REQUIRED'),
    (subscription(), {'whatsapp_numbers': True}, 'WHATSAPP_ENTITLEMENT_REQUIRED'),
    (subscription(), {'whatsapp_numbers': 0}, 'WHATSAPP_ENTITLEMENT_REQUIRED'),
    (subscription(), {'whatsapp_numbers': 1}, None),
])
def test_effective_subscription_gate_is_atomic(monkeypatch, sub, entitlements, code):
    db = Mock()
    monkeypatch.setattr(service.billing, 'subscription_for', lambda *a, **k: sub)
    db.get.return_value = NS(entitlements=entitlements)
    row = request()
    if code:
        with pytest.raises(HTTPException) as error:
            service.transition(db, row, NS(id=4, tenant_id=3, organization_id=5), 'accepted')
        assert error.value.status_code == 409
        assert isinstance(error.value.detail, dict)
        assert cast(dict[str, object], error.value.detail)['code'] == code
        assert row.status == 'requested' and row.history == [] and row.assigned_admin_id is None
        db.add.assert_not_called()
    else:
        service.transition(db, row, NS(id=4, tenant_id=3, organization_id=5), 'accepted')
        assert row.status == 'accepted' and row.accepted_at and row.assigned_admin_id == 4
        assert row.history[-1]['event'] == 'accepted'


def test_subscription_retry_and_expiry_after_acceptance(monkeypatch):
    db = Mock(); db.get.return_value = NS(entitlements={'whatsapp_numbers': 1})
    sub = subscription(status='cancelled')
    monkeypatch.setattr(service.billing, 'subscription_for', lambda *a, **k: sub)
    row = request(); actor = NS(id=4, tenant_id=3, organization_id=5)
    with pytest.raises(HTTPException): service.transition(db, row, actor, 'accepted')
    sub.status = 'active'
    service.transition(db, row, actor, 'accepted')
    sub.current_end = datetime.now(UTC) - timedelta(seconds=1)
    with pytest.raises(HTTPException): service.transition(db, row, actor, 'setup_in_progress')
    assert row.status == 'accepted'


@pytest.mark.parametrize('from_status,to_status', [('requested','connected'), ('requested','setup_in_progress'), ('accepted','connected'), ('rejected','accepted'), ('connected','requested'), ('requested','action_required')])
def test_invalid_transition_cannot_skip_steps(from_status, to_status):
    with pytest.raises(HTTPException) as error:
        service.transition(Mock(), request(from_status), NS(id=4), to_status)
    assert isinstance(error.value.detail, dict)
    assert cast(dict[str, object], error.value.detail)['code'] == 'INVALID_TRANSITION'


def test_rejection_requires_reason_and_preserves_history():
    row = request(); db = Mock(); actor = NS(id=4, tenant_id=3, organization_id=5)
    with pytest.raises(HTTPException): service.transition(db, row, actor, 'rejected', '   ')
    service.transition(db, row, actor, 'rejected', 'Number belongs to another business')
    assert row.rejection_reason == 'Number belongs to another business'
    assert row.history[-1]['previous_status'] == 'requested'


def test_tenant_confirmation_does_not_activate_and_is_idempotent():
    row = request('action_required'); db = Mock(); db.scalar.return_value = row
    actor = NS(id=4, tenant_id=1, organization_id=2)
    # Serialization helper needs a real model; inspect state directly instead.
    from app.models.saas import OnboardingRequest
    real = OnboardingRequest(id='request', tenant_id=1, organization_id=2, status='action_required', history=[])
    db.scalar.return_value = real
    verification_completed('request', cast(Any, actor), db)
    verification_completed('request', cast(Any, actor), db)
    assert real.status == 'action_required' and real.tenant_confirmed_at
    assert len(real.history) == 1
    db.commit.assert_called_once()


def test_cross_tenant_confirmation_returns_not_found():
    db = Mock(); db.scalar.return_value = None
    with pytest.raises(HTTPException) as error:
        verification_completed('other-request', cast(Any, NS(id=4, tenant_id=1, organization_id=2)), db)
    assert error.value.status_code == 404
    params = db.scalar.call_args.args[0].compile().params
    assert params['tenant_id_1'] == 1 and params['organization_id_1'] == 2


@pytest.mark.parametrize('phone', ['123', 'letters', '090000000000', '+919000000000', '919000000000000000'])
def test_invalid_request_phone(phone):
    with pytest.raises(ValidationError): OnboardingPayload(phone=phone, business_name='Business')


def test_blank_business_and_untrusted_status_fields_are_rejected():
    with pytest.raises(ValidationError): OnboardingPayload(phone='919000000000', business_name='  ')
    with pytest.raises(ValidationError): OnboardingUpdate(status='ready', customer_message='Bypass')
    with pytest.raises(ValidationError): OnboardingPayload(phone='919000000000', business_name='Business', **{'tenant_id': 99})


def test_tenant_admin_is_not_platform_staff():
    db = Mock(); db.get.return_value = None
    with pytest.raises(HTTPException) as error:
        staff_permission('onboarding.manage')(cast(Any, NS(id=4, role='admin')), db)
    assert error.value.status_code == 403


def test_request_action_and_resume_keep_confirmation_history(monkeypatch):
    monkeypatch.setattr(service, 'require_eligible', lambda *a: None)
    db = Mock(); row = request('setup_in_progress'); actor = NS(id=4, tenant_id=3, organization_id=5)
    service.transition(db, row, actor, 'action_required', 'Authorize your own business', 'meta_authorization')
    assert row.required_action == 'meta_authorization' and row.action_requested_at
    service.transition(db, row, actor, 'setup_in_progress')
    assert row.status == 'setup_in_progress' and len(row.history) == 2


def provider(monkeypatch):
    monkeypatch.setattr(service, 'decrypt_token', lambda *a: 'private')
    monkeypatch.setattr(service, 'get_settings', lambda: NS(meta_app_id='111', meta_app_secret='secret'))
    assets = [{'waba_id':'444', 'phone_number_id':'333', 'display_phone_number':'+919000000000'}]
    monkeypatch.setattr(service, 'authorized_assets', lambda token: (assets, None))
    def graph(path, *args, **kwargs):
        if path.endswith('/subscribed_apps'): return {'data':[{'whatsapp_business_api_data':{'id':'111'}}]}
        if path.endswith('/subscriptions'): return {'data':[{'object':'whatsapp_business_account', 'active':True, 'fields':[{'name':'messages'}]}]}
        return {'messages':[{'id':'wamid.test'}]}
    monkeypatch.setattr(service, 'graph', graph)
    return NS(id=1, tenant_id=1, organization_id=2, waba_id='444', phone_number_id='333', encrypted_access_token='encrypted',
              updated_at=datetime.now(UTC), display_phone_number='+919000000000')


def test_wrong_tenant_and_number_rejected(monkeypatch):
    connection = provider(monkeypatch); row = request()
    connection.organization_id = 99
    with pytest.raises(HTTPException): service.provider_checks(connection, row)
    connection.organization_id = 2; row.phone = '919000000001'
    with pytest.raises(HTTPException) as error: service.provider_checks(connection, row)
    assert cast(dict[str, object], error.value.detail)['code'] == 'PHONE_MISMATCH'


def test_invalid_authorization_and_failed_webhook_rejected(monkeypatch):
    connection = provider(monkeypatch); row = request()
    monkeypatch.setattr(service, 'authorized_assets', Mock(side_effect=HTTPException(400, 'Invalid authorization')))
    with pytest.raises(HTTPException): service.provider_checks(connection, row)
    connection = provider(monkeypatch)
    monkeypatch.setattr(service, 'graph', lambda *a, **k: {'data':[]})
    with pytest.raises(HTTPException) as error: service.provider_checks(connection, row)
    assert cast(dict[str, object], error.value.detail)['code'] == 'WEBHOOK_NOT_CONFIGURED'


def test_verification_requires_consent_and_successful_test(monkeypatch):
    connection = provider(monkeypatch); row = request('setup_in_progress'); db = Mock()
    monkeypatch.setattr(service, 'matching_connection', lambda *a: connection)
    monkeypatch.setattr(service, 'require_eligible', lambda *a: None)
    payload = VerificationPayload(test_phone='919000000001', template_name='approved_test', language='en_US')
    actor = NS(id=4, tenant_id=3, organization_id=5)
    db.scalar.return_value = None
    with pytest.raises(HTTPException): service.verify(db, row, actor, payload)
    assert row.verification == {}
    db.scalar.return_value = NS(opted_in=True)
    original = service.graph
    monkeypatch.setattr(service, 'graph', lambda path, *a, **k: {} if path.endswith('/messages') else original(path, *a, **k))
    with pytest.raises(HTTPException) as error: service.verify(db, row, actor, payload)
    assert cast(dict[str, object], error.value.detail)['code'] == 'TEST_MESSAGE_FAILED'
    monkeypatch.setattr(service, 'graph', original)
    service.verify(db, row, actor, payload)
    assert row.status == 'setup_in_progress' and row.verification['test_result'] == 'accepted'
    db.scalar.return_value = NS(status='accepted')
    call_count = db.add.call_count
    service.verify(db, row, actor, payload)
    assert db.add.call_count == call_count  # Retry cannot resend or create duplicate evidence.
    with pytest.raises(HTTPException) as error: service.require_verified(db, row)
    assert cast(dict[str, object], error.value.detail)['code'] == 'TEST_DELIVERY_REQUIRED'
    db.scalar.return_value = NS(status='delivered')
    service.transition(db, row, actor, 'connected')
    assert row.status == 'connected' and row.connected_at and row.verified_by == 4


def test_subscription_expiry_prevents_connect_before_provider_calls(monkeypatch):
    monkeypatch.setattr(service.billing, 'subscription_for', lambda *a, **k: subscription(end=-1,start=-2))
    verify = Mock(); monkeypatch.setattr(service, 'require_verified', verify)
    row = request('setup_in_progress')
    with pytest.raises(HTTPException): service.transition(Mock(), row, NS(id=4), 'connected')
    verify.assert_not_called(); assert row.status == 'setup_in_progress'


@pytest.mark.parametrize('status', ['accepted', 'sent', 'failed', 'delivered', 'read'])
def test_connect_requires_successful_latest_test(monkeypatch, status):
    connection = provider(monkeypatch)
    monkeypatch.setattr(service, 'matching_connection', lambda *a: connection)
    monkeypatch.setattr(service, 'require_eligible', lambda *a: None)
    row = request('setup_in_progress')
    row.verification = {'authorization': True, 'phone_match': True, 'webhook': True,
        'checked_at': datetime.now(UTC).isoformat(), 'connection_id': connection.id,
        'connection_updated_at': connection.updated_at.isoformat(),
        'test_message_id': 'wamid.test', 'test_phone': '919000000001'}
    db = Mock()
    db.scalar.return_value = NS(status=status)
    if status in {'delivered', 'read'}:
        service.require_verified(db, row)
        assert row.verification['test_result'] == status
    else:
        with pytest.raises(HTTPException) as error:
            service.require_verified(db, row)
        assert cast(dict[str, object], error.value.detail)['code'] == 'TEST_DELIVERY_REQUIRED'


def test_failed_test_has_retry_cooldown_and_preserves_evidence(monkeypatch):
    connection = provider(monkeypatch)
    monkeypatch.setattr(service, 'matching_connection', lambda *a: connection)
    monkeypatch.setattr(service, 'require_eligible', lambda *a: None)
    row = request('setup_in_progress')
    row.verification = {'checked_at': datetime.now(UTC).isoformat(), 'test_message_id': 'old'}
    with pytest.raises(HTTPException) as error:
        service.verify(Mock(), row, NS(id=4), VerificationPayload(
            test_phone='919000000001', template_name='approved_test', language='en_US'))
    assert cast(dict[str, object], error.value.detail)['code'] == 'TEST_RETRY_COOLDOWN'
    assert row.verification['test_message_id'] == 'old'
