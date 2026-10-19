from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from app.routers.webhooks import apply_change
from app.services import onboarding


@pytest.mark.parametrize('state', ['sent', 'delivered', 'read', 'failed'])
def test_record_diagnostics_and_campaign_processing(state):
    record = NS(status='accepted', status_timestamp=0, delivery_details={})
    db = Mock()
    db.scalar.return_value = record
    db.scalars.return_value.all.return_value = []
    connection = NS(tenant_id=1, organization_id=2, phone_number_id='333')
    event = {'id': 'wamid.test', 'status': state, 'timestamp': '100',
             'errors': [{'code': 131047, 'message': 'Provider reason',
                         'error_data': {'details': 'Provider details'}}]}
    apply_change(db, connection, {'statuses': [event]})
    assert record.status == state
    assert record.delivery_details['webhook_received_at']
    assert record.delivery_details['status_updated_at']
    if state == 'failed':
        assert record.delivery_details['error'] == event['errors']
    else:
        assert record.delivery_details[state + '_at']
    original = dict(record.delivery_details)
    apply_change(db, connection, {'statuses': [event]})
    for key in original.keys() - {'webhook_received_at'}:
        assert record.delivery_details[key] == original[key]
    apply_change(db, connection, {'statuses': [{**event, 'status': 'sent', 'timestamp': '90'}]})
    assert record.status == state
    params = db.scalar.call_args.args[0].compile().params
    assert params['tenant_id_1'] == 1
    assert params['organization_id_1'] == 2
    assert params['sender_phone_id_1'] == '333'
    db.scalars.assert_called()  # Existing campaign processing still runs.


def test_unknown_message_is_safe():
    db = Mock()
    db.scalar.return_value = None
    db.scalars.return_value.all.return_value = []
    apply_change(db, NS(tenant_id=1, organization_id=2, phone_number_id='333'),
                 {'statuses': [{'id': 'unknown', 'status': 'delivered', 'timestamp': '100'}]})


@pytest.mark.parametrize('state', ['accepted', 'sent', 'delivered', 'read', 'failed', None])
def test_public_request_reads_scoped_latest_status(monkeypatch, state):
    row = NS(tenant_id=1, organization_id=2, verification={
        'test_message_id': 'wamid.test', 'phone_number_id': '333',
        'test_phone': '919000000001', 'test_result': 'accepted'})
    monkeypatch.setattr(onboarding, 'model_to_dict', lambda value: {'verification': value.verification})
    monkeypatch.setattr(onboarding.billing, 'subscription_for', lambda *a: None)
    monkeypatch.setattr(onboarding, 'eligibility', lambda *a: None)
    db = Mock()
    db.scalar.return_value = NS(status=state, delivery_details={'webhook_received_at': 'now'}) if state else None
    result = onboarding.public_request(db, row)['verification']
    assert result['test_result'] == (state or 'accepted')
    assert result['callback_received'] is bool(state)
    assert row.verification['test_result'] == 'accepted'
    params = db.scalar.call_args.args[0].compile().params
    assert params['tenant_id_1'] == 1 and params['organization_id_1'] == 2
    assert params['sender_phone_id_1'] == '333'
    assert params['recipient_1'] == '919000000001'
