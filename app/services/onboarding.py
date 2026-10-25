"""Admin-managed onboarding; provider authorization never activates messaging."""
import re
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import select

from app.models import Organization, WhatsAppConnection
from app.models.saas import OnboardingRequest, SubscriptionPlan
from app.services import billing
from app.services.audit import audit
from app.services.whatsapp_connections import authorized_assets, decrypt_token, graph
from app.config.settings import get_settings
from app.utils.helpers import model_to_dict

ACTIVE = {'requested', 'accepted', 'setup_in_progress', 'action_required',
          'needs_customer_action', 'provider_review', 'billing_pending'}
TRANSITIONS = {
    'requested': {'accepted', 'rejected', 'cancelled'},
    'accepted': {'setup_in_progress', 'cancelled', 'failed'},
    'setup_in_progress': {'action_required', 'connected', 'failed', 'cancelled'},
    'action_required': {'setup_in_progress', 'failed', 'cancelled'},
}


def conflict(code, message):
    raise HTTPException(409, {'code': code, 'message': message})


def scope(row):
    return SimpleNamespace(tenant_id=row.tenant_id, organization_id=row.organization_id)


def eligibility(db, row, lock=False):
    subscription = billing.subscription_for(db, scope(row), lock=lock)
    status = billing.effective_status(subscription)
    if not subscription:
        return 'SUBSCRIPTION_NOT_FOUND', 'This tenant does not have an active subscription plan. Please activate or renew an eligible subscription before accepting the WhatsApp onboarding request.'
    if status != 'active':
        return ('SUBSCRIPTION_EXPIRED' if status == 'expired' else 'SUBSCRIPTION_NOT_ACTIVE'), 'This tenant does not have an active subscription plan. Please activate or renew an eligible subscription before continuing WhatsApp onboarding.'
    plan = db.get(SubscriptionPlan, subscription.plan_id)
    limit = (plan.entitlements or {}).get('whatsapp_numbers') if plan else None
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        return 'WHATSAPP_ENTITLEMENT_REQUIRED', "This tenant's current subscription does not include WhatsApp onboarding. Please assign an eligible plan before accepting this request."
    return None


def require_eligible(db, row):
    # Organization locks serialize staff mutations with manual subscription operations.
    # Runtime billing reads must not require UPDATE privileges on subscriptions.
    error = eligibility(db, row)
    if error:
        conflict(*error)


def locked(db, request_id):
    # Same lock order as subscription assignment: organization, then subscription/request.
    row = db.get(OnboardingRequest, request_id)
    if not row:
        raise HTTPException(404, 'Onboarding request not found')
    organization = db.scalar(select(Organization).where(Organization.id == row.organization_id,
        Organization.tenant_id == row.tenant_id).with_for_update())
    if not organization:
        raise HTTPException(404, 'Business organization not found')
    return db.scalar(select(OnboardingRequest).where(OnboardingRequest.id == request_id)
                     .with_for_update().execution_options(populate_existing=True))


def record(row, actor, event, **details):
    stamp = datetime.now(UTC).isoformat()
    row.history = [*(row.history or []), {'event': event, 'actor_id': actor.id,
                                         'at': stamp, **details}]


def transition(db, row, actor, status, message=None, required_action=None):
    if status not in TRANSITIONS.get(row.status, set()):
        conflict('INVALID_TRANSITION', f'Cannot change {row.status} to {status}')
    if status in {'accepted', 'setup_in_progress', 'connected'}:
        require_eligible(db, row)
    if status in {'rejected', 'action_required', 'failed', 'cancelled'} and not str(message or '').strip():
        raise HTTPException(422, 'A reason or instructions are required')
    if status == 'action_required' and required_action not in {'meta_authorization', 'phone_verification', 'business_verification', 'other'}:
        raise HTTPException(422, 'Select a required tenant action')
    if status == 'connected':
        require_verified(db, row)
    previous = row.status
    row.status = status
    row.assigned_admin_id = actor.id
    now = datetime.now(UTC)
    if status == 'accepted':
        row.accepted_at = now
    if status == 'setup_in_progress':
        row.setup_started_at = row.setup_started_at or now
    if status == 'action_required':
        row.required_action = required_action
        row.action_requested_at = now
        row.tenant_confirmed_at = None
    if status == 'rejected':
        row.rejection_reason = message.strip()
    if status == 'connected':
        row.connected_at = now
        row.verified_by = actor.id
    if message is not None:
        row.customer_message = message.strip()
    if status != 'connected':
        row.verification = {}  # Every setup change invalidates previous evidence.
    record(row, actor, status, previous_status=previous)
    audit(db, actor, 'platform.onboarding.updated', row.id,
          {'status': status, 'target_tenant': row.tenant_id, 'target_organization': row.organization_id})
    return row


def matching_connection(db, row):
    connections = db.scalars(select(WhatsAppConnection).where(
        WhatsAppConnection.tenant_id == row.tenant_id,
        WhatsAppConnection.organization_id == row.organization_id)).all()
    return next((connection for connection in connections if
                 re.sub(r'\D', '', connection.display_phone_number or '') == row.phone), None)


def provider_checks(connection, row):
    if not connection or connection.tenant_id != row.tenant_id or connection.organization_id != row.organization_id:
        conflict('CONNECTION_NOT_FOUND', 'Authorize the approved WhatsApp number for this organization first')
    token = decrypt_token(connection.encrypted_access_token, row.tenant_id, row.organization_id)
    assets, _ = authorized_assets(token)
    asset = next((asset for asset in assets if asset['waba_id'] == connection.waba_id
                  and asset['phone_number_id'] == connection.phone_number_id), None)
    if not asset or re.sub(r'\D', '', asset.get('display_phone_number') or '') != row.phone:
        conflict('PHONE_MISMATCH', 'Meta authorization does not match the approved business number')
    apps = graph(connection.waba_id + '/subscribed_apps', token).get('data', [])
    if not any(str((app.get('whatsapp_business_api_data') or {}).get('id')) == get_settings().meta_app_id for app in apps):
        conflict('WEBHOOK_NOT_CONFIGURED', 'The WhatsApp account is not subscribed to this application')
    subscriptions = graph(get_settings().meta_app_id + '/subscriptions',
        get_settings().meta_app_id + '|' + get_settings().meta_app_secret).get('data', [])
    if not any(item.get('object') == 'whatsapp_business_account' and item.get('active') is True
               and any(field.get('name') == 'messages' for field in item.get('fields', []))
               for item in subscriptions):
        conflict('WEBHOOK_NOT_CONFIGURED', 'Configure an active WhatsApp messages webhook for this Meta application')
    return token


def verify(db, row, actor, payload):
    if row.status != 'setup_in_progress':
        conflict('INVALID_TRANSITION', 'Resume setup before verifying the connection')
    require_eligible(db, row)
    connection = matching_connection(db, row)
    token = provider_checks(connection, row)
    evidence = row.verification or {}
    if (evidence.get('connection_id') == connection.id
            and evidence.get('connection_updated_at') == connection.updated_at.isoformat()
            and evidence.get('test_phone') == payload.test_phone
            and evidence.get('template_name') == payload.template_name
            and evidence.get('language') == payload.language
            and evidence.get('checked_at')
            and datetime.fromisoformat(evidence['checked_at']) > datetime.now(UTC) - timedelta(minutes=30)):
        from app.models.saas import MessageRecord
        previous = db.scalar(select(MessageRecord).where(MessageRecord.tenant_id == row.tenant_id,
            MessageRecord.organization_id == row.organization_id,
            MessageRecord.sender_phone_id == connection.phone_number_id,
            MessageRecord.provider_message_id == evidence.get('test_message_id')))
        if previous and previous.status in {'accepted', 'sent', 'delivered', 'read'}:
            # A response retry cannot send another real test message.
            return 'reused'
    if evidence.get('checked_at') and datetime.fromisoformat(evidence['checked_at']) > datetime.now(UTC) - timedelta(minutes=1):
        conflict('TEST_RETRY_COOLDOWN', 'Wait one minute after the last test before retrying')
    from app.database.authorization import staff_scope
    staff_scope(db, actor, 'onboarding.manage', resource=row.id, action='platform.onboarding.updated',
                target_tenant=row.tenant_id, target_org=row.organization_id,
                test_phone=payload.test_phone, test_sender=connection.phone_number_id)
    # Use a consented recipient and an approved template; never free-form marketing.
    from app.models.saas import ContactConsent
    consent = db.scalar(select(ContactConsent).where(ContactConsent.tenant_id == row.tenant_id,
        ContactConsent.organization_id == row.organization_id, ContactConsent.phone == payload.test_phone,
        ContactConsent.opted_in.is_(True)))
    if not consent:
        raise HTTPException(422, 'Record explicit messaging consent for the test recipient first')
    from app.services.whatsapp_interlock import require_sending_enabled
    require_sending_enabled()
    result = graph(connection.phone_number_id + '/messages', token, method='POST', data={
        'messaging_product': 'whatsapp', 'to': payload.test_phone, 'type': 'template',
        'template': {'name': payload.template_name, 'language': {'code': payload.language}}})
    messages = result.get('messages') or []
    if not messages or not isinstance(messages[0], dict) or not messages[0].get('id'):
        conflict('TEST_MESSAGE_FAILED', 'Meta did not accept the permitted test message')
    require_eligible(db, row)  # Provider calls can cross the subscription expiry instant.
    # Provider acceptance is recorded separately from actual delivery.
    from app.models.saas import MessageRecord
    db.add(MessageRecord(tenant_id=row.tenant_id, organization_id=row.organization_id,
        provider_message_id=messages[0]['id'], sender_phone_id=connection.phone_number_id,
        recipient=payload.test_phone, status='accepted'))
    row.verification = {'authorization': True, 'phone_match': True, 'webhook': True,
        'test_message_id': messages[0]['id'], 'test_result': 'accepted',
        'connection_id': connection.id, 'phone_number_id': connection.phone_number_id,
        'waba_id': connection.waba_id, 'display_phone_number': connection.display_phone_number,
        'connection_updated_at': connection.updated_at.isoformat(),
        'test_phone': payload.test_phone, 'template_name': payload.template_name, 'language': payload.language,
        'checked_at': datetime.now(UTC).isoformat()}
    row.verified_at = datetime.now(UTC)
    row.verified_by = actor.id
    record(row, actor, 'verification_submitted')
    audit(db, actor, 'platform.onboarding.updated', row.id, {'verification': 'test_accepted'})
    return 'sent'


def require_verified(db, row):
    evidence = row.verification or {}
    if not all(evidence.get(key) is True for key in ('authorization', 'phone_match', 'webhook')):
        conflict('VERIFICATION_REQUIRED', 'All provider verification checks must pass')
    if not evidence.get('checked_at') or datetime.fromisoformat(evidence['checked_at']) < datetime.now(UTC) - timedelta(minutes=30):
        conflict('VERIFICATION_REQUIRED', 'Verify the connection again; verification is missing or older than 30 minutes')
    connection = matching_connection(db, row)
    if not connection or connection.id != evidence.get('connection_id') or connection.updated_at.isoformat() != evidence.get('connection_updated_at'):
        conflict('VERIFICATION_REQUIRED', 'Connection changed after verification; verify again')
    provider_checks(connection, row)
    from app.models.saas import MessageRecord
    message = db.scalar(select(MessageRecord).where(MessageRecord.tenant_id == row.tenant_id,
        MessageRecord.organization_id == row.organization_id,
        MessageRecord.sender_phone_id == connection.phone_number_id,
        MessageRecord.recipient == evidence.get('test_phone'),
        MessageRecord.provider_message_id == evidence.get('test_message_id')))
    if not message or message.status not in {'delivered', 'read'}:
        conflict('TEST_DELIVERY_REQUIRED', 'Wait for the signed Meta webhook to confirm test message delivery before connecting')
    require_eligible(db, row)
    row.verification = {**evidence, 'test_result': message.status}


def public_request(db, row):
    data = model_to_dict(row)
    evidence = dict(row.verification or {})
    if evidence.get('test_message_id') and evidence.get('phone_number_id'):
        from app.models.saas import MessageRecord
        message = db.scalar(select(MessageRecord).where(
            MessageRecord.tenant_id == row.tenant_id,
            MessageRecord.organization_id == row.organization_id,
            MessageRecord.sender_phone_id == evidence['phone_number_id'],
            MessageRecord.recipient == evidence.get('test_phone'),
            MessageRecord.provider_message_id == evidence['test_message_id']))
        if message:
            evidence.update(message.delivery_details or {})
            evidence['test_result'] = message.status
        evidence['api_acceptance'] = 'accepted'
        evidence['callback_received'] = bool(evidence.get('webhook_received_at'))
        data['verification'] = evidence
    subscription = billing.subscription_for(db, scope(row))
    data['subscription_status'] = billing.effective_status(subscription) or 'none'
    data['eligibility_error'] = eligibility(db, row)
    return data


def require_tenant_authorization(db, user):
    db.scalar(select(Organization).where(Organization.tenant_id == user.tenant_id,
        Organization.id == user.organization_id).with_for_update())
    row = db.scalar(select(OnboardingRequest).where(OnboardingRequest.tenant_id == user.tenant_id,
        OnboardingRequest.organization_id == user.organization_id,
        OnboardingRequest.status == 'action_required',
        OnboardingRequest.required_action == 'meta_authorization').with_for_update())
    if not row:
        raise HTTPException(403, 'Request setup assistance; an administrator must request Meta authorization first')
    require_eligible(db, row)
    return row
