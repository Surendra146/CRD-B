import copy
import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select

from app.models import WhatsAppTemplate, Organization
from app.services.security import ensure_tenant_access
from app.services.whatsapp_connections import resolve_credentials, graph
from app.services.template_definitions import compile_draft, outgoing, provider_definition
from app.services.template_media import asset, sample_handle, sending_media
from app.services.template_definitions import rejection_reason, draft_signature, media_signature, has_unpublished_edits, editable_signature


def timestamp():
    return datetime.now(UTC).isoformat()


def owned(db, user, template_id, lock=False):
    query = select(WhatsAppTemplate).where(WhatsAppTemplate.id == template_id,
        WhatsAppTemplate.tenant_id == user.tenant_id, WhatsAppTemplate.organization_id == user.organization_id)
    row = db.scalar(query.with_for_update().execution_options(populate_existing=True) if lock else query)
    return ensure_tenant_access(row, user, 'Template')


def approved_definition(row):
    definition = (row.workflow or {}).get('approved')
    if not definition and (row.stats or {}).get('meta_status') == 'APPROVED':
        definition = provider_definition({'id': (row.targeting or {}).get('meta_id'),
            'name': row.whatsapp_template_name, 'category': row.category,
            'language': (row.content or {}).get('language'), 'components': (row.content or {}).get('components', [])})
        definition['waba_id'] = (row.targeting or {}).get('waba_id')
    return definition


def merge_provider(row, item, waba_id, sender, started=None):
    workflow = copy.deepcopy(row.workflow or {})
    if started and workflow.get('submitted_at', '') > started:
        return False
    previous = workflow.get('submitted')
    submitted_match = previous and str(previous.get('meta_id')) == str(item['id'])
    approved = workflow.get('approved')
    if not submitted_match and approved and str(approved.get('meta_id')) != str(item['id']):
        # A new submission owns this row; unrelated IDs must never replace it.
        return False
    definition = provider_definition(item, previous if submitted_match else approved)
    definition.update(waba_id=waba_id, sender_phone_number_id=sender)
    if not previous and not approved and item['status'] != 'APPROVED':
        workflow['submitted'] = definition
    if submitted_match or not previous:
        workflow.update(status=item['status'], rejection_reason=rejection_reason(item.get('rejected_reason')), synced_at=timestamp())
    if item['status'] == 'APPROVED':
        if approved and approved.get('meta_id') != definition.get('meta_id'):
            workflow['approved_history'] = [*workflow.get('approved_history', []), approved]
        workflow['approved'] = definition
        row.targeting = {**(row.targeting or {}), 'waba_id': waba_id, 'meta_id': str(item['id'])}
        row.whatsapp_template_name = item['name']
        row.stats = {**(row.stats or {}), 'meta_status': 'APPROVED', 'synced_at': timestamp()}
        row.is_active = True
    elif approved and str(approved.get('meta_id')) == str(item['id']):
        row.stats = {**(row.stats or {}), 'meta_status': item['status'], 'synced_at': timestamp()}
        row.is_active = False
    elif not approved:
        row.targeting = {**(row.targeting or {}), 'waba_id': waba_id, 'meta_id': str(item['id'])}
        row.stats = {**(row.stats or {}), 'meta_status': item['status'], 'synced_at': timestamp()}
        row.is_active = item['status'] == 'APPROVED'
    row.workflow = workflow
    if workflow.get('draft_baseline') and (submitted_match or not previous):
        baseline = workflow['draft_baseline']
        signature = editable_signature(definition['name'], definition['category'], definition)
        # Generated revision names belong to the submission, not the editable name.
        signature['name'] = baseline['definition']['name']
        workflow['draft_baseline'] = {**baseline, 'definition': signature}
        row.workflow = workflow
    if not workflow.get('draft_baseline') and not has_unpublished_edits(row):
        row.workflow = {**workflow, 'draft_baseline': {'definition': draft_signature(row), 'media': media_signature(row)}}
    return True


def submit(db, user, template_id):
    # Serialize name reservation within the organization, including distinct rows.
    db.scalar(select(Organization).where(Organization.id == user.organization_id).with_for_update())
    row = owned(db, user, template_id, lock=True)
    workflow = copy.deepcopy(row.workflow or {})
    if workflow.get('status') in {'SUBMITTING', 'SUBMISSION_UNKNOWN', 'PENDING', 'IN_APPEAL'}:
        raise HTTPException(409, 'Submission already exists. Refresh its status before submitting again')
    content = copy.deepcopy(row.content or {})
    fingerprint = hashlib.sha256(json.dumps({'content': content, 'category': row.category}, sort_keys=True).encode()).hexdigest()
    if workflow.get('status') == 'APPROVED' and workflow.get('submitted_fingerprint') == fingerprint:
        raise HTTPException(409, 'This draft has already been approved. Edit its content before submitting another version')
    connection = resolve_credentials(db, user, content.get('sender_phone_number_id'))
    if not connection.whatsapp_waba_id:
        raise HTTPException(409, 'The sending account has no connected WABA')
    name = content.get('meta_name') or row.whatsapp_template_name or row.name
    if workflow.get('submitted_fingerprint') == fingerprint and workflow.get('status') in {'SUBMISSION_FAILED', 'SUBMISSION_NOT_FOUND'}:
        name = workflow['submitted']['name']
    elif approved_definition(row) or workflow.get('submitted'):
        name = name[:495] + '_r' + uuid4().hex[:8]
    definition = compile_draft(name, row.category, content)
    definition.update(waba_id=connection.whatsapp_waba_id, sender_phone_number_id=connection.whatsapp_phone_number_id)
    peers = db.scalars(select(WhatsAppTemplate).where(WhatsAppTemplate.tenant_id == user.tenant_id,
        WhatsAppTemplate.organization_id == user.organization_id, WhatsAppTemplate.id != row.id)).all()
    if any(d.get('name') == name and d.get('waba_id', (p.targeting or {}).get('waba_id')) == connection.whatsapp_waba_id and
           d.get('language') == definition['language'] for p in peers
           for d in [(p.workflow or {}).get('submitted') or {}, approved_definition(p) or {}]):
        raise HTTPException(409, 'This name and language are already submitted for this WABA')
    if definition.get('sample_asset_id'):
        asset(row, definition['sample_asset_id'], definition['header_type'])
        handle = sample_handle(row, definition['sample_asset_id'], connection)
        definition['components'][0]['example'] = {'header_handle': [handle]}
    workflow.update(status='SUBMITTING', submitted=definition, submitted_at=timestamp(), rejection_reason=None,
                    submitted_revision=workflow.get('draft_revision', 1), submitted_fingerprint=fingerprint, submission_error=None)
    workflow['draft_baseline'] = {'definition': draft_signature(row), 'media': media_signature(row)}
    row.workflow = workflow
    db.commit()  # A timeout/restart leaves an explicit reconciliation state.
    try:
        result = graph(connection.whatsapp_waba_id + '/message_templates', connection.whatsapp_access_token,
                       method='POST', data={k: definition[k] for k in ('name', 'language', 'category', 'components')})
        if not result.get('id'):
            raise HTTPException(502, 'Meta did not return a template ID; refresh before retrying')
    except HTTPException as error:
        row = owned(db, user, template_id, lock=True)
        known_failure = isinstance(error.detail, dict) and error.detail.get('code') in {10, 100, 190, 200, 131008, 131009}
        row.workflow = {**row.workflow, 'status': 'SUBMISSION_FAILED' if known_failure else 'SUBMISSION_UNKNOWN',
                        'submission_error': 'Meta rejected submission. Correct the draft and retry.' if known_failure else 'Meta acceptance is uncertain. Refresh by name before retrying.'}
        db.commit()
        raise error
    row = owned(db, user, template_id, lock=True)
    definition['meta_id'] = str(result['id'])
    row.workflow = {**row.workflow, 'submitted': definition, 'status': result.get('status', 'PENDING')}
    merge_provider(row, {**definition, 'id': result['id'], 'status': result.get('status', 'PENDING')},
                   connection.whatsapp_waba_id, connection.whatsapp_phone_number_id)
    db.commit()
    return row


def refresh(db, user, template_id):
    row = owned(db, user, template_id, lock=True)
    definition = (row.workflow or {}).get('submitted') or approved_definition(row)
    if not definition:
        raise HTTPException(409, 'Save and submit this draft first')
    connection = resolve_credentials(db, user, definition.get('sender_phone_number_id'))
    if connection.whatsapp_waba_id != definition.get('waba_id'):
        raise HTTPException(409, 'Reconnect the original WABA before refreshing this template')
    if definition.get('meta_id'):
        item = graph(definition['meta_id'], connection.whatsapp_access_token,
                     params={'fields': 'id,name,status,category,language,components,rejected_reason'})
    else:
        response = graph(connection.whatsapp_waba_id + '/message_templates', connection.whatsapp_access_token,
                         params={'name': definition['name'], 'fields': 'id,name,status,category,language,components,rejected_reason', 'limit': 100})
        item = next((i for i in response.get('data', []) if i['name'] == definition['name'] and i['language'] == definition['language']), None)
        if not item:
            submitted_at = (row.workflow or {}).get('submitted_at')
            if submitted_at and (datetime.now(UTC) - datetime.fromisoformat(submitted_at)).total_seconds() >= 300:
                # A subsequent retry reuses this exact name/language. Meta's name
                # uniqueness prevents a second version if acceptance was delayed.
                row.workflow = {**row.workflow, 'status': 'SUBMISSION_NOT_FOUND', 'synced_at': timestamp(),
                                'submission_error': 'Meta has not listed this submission after five minutes. Retry will reuse the reserved name.'}
                db.commit()
                return row
            raise HTTPException(409, 'Meta has not returned this submission yet. Refresh later; verify in WhatsApp Manager before retrying')
        row.workflow = {**row.workflow, 'submitted': {**definition, 'meta_id': str(item['id'])}}
    merge_provider(row, item, connection.whatsapp_waba_id, connection.whatsapp_phone_number_id)
    db.commit()
    return row


def prepare_send(db, user, request, connection, recipient):
    selected = request.get('template')
    if not selected:
        return None, None
    if not isinstance(selected, dict):
        raise HTTPException(422, 'Select an approved template')
    if selected.get('id'):
        row = owned(db, user, selected['id'])
    else:
        rows = db.scalars(select(WhatsAppTemplate).where(WhatsAppTemplate.tenant_id == user.tenant_id,
            WhatsAppTemplate.organization_id == user.organization_id,
            WhatsAppTemplate.targeting['waba_id'].as_string() == connection.whatsapp_waba_id)).all()
        row = next((r for r in rows if (approved_definition(r) or {}).get('name') == selected.get('name') and
            (approved_definition(r) or {}).get('language') == (selected.get('language') or {}).get('code')), None)
        if not row:
            raise HTTPException(409, 'Synchronize and select an approved template for this WABA')
    definition = approved_definition(row)
    if not definition or not row.is_active or (row.stats or {}).get('meta_status') != 'APPROVED':
        raise HTTPException(409, 'This template is not approved for sending')
    if definition.get('waba_id', (row.targeting or {}).get('waba_id')) != connection.whatsapp_waba_id:
        raise HTTPException(409, 'Template and sending account belong to different WABAs')
    media_asset = selected.get('media_asset_id')
    if definition.get('header_type') in {'IMAGE', 'VIDEO', 'DOCUMENT'}:
        asset(row, media_asset, definition['header_type'])
    elif media_asset:
        raise HTTPException(422, 'This approved template does not have a media header')
    payload = outgoing(definition, recipient, 'VALIDATE_ONLY' if media_asset else None, selected.get('mappings'))
    snapshot = {'template_id': row.id, 'definition': copy.deepcopy(definition), 'asset_id': media_asset,
                'mappings': selected.get('mappings') or {}}
    return payload, snapshot


def hydrate_media(db, user, payload, snapshot, connection):
    if not snapshot or not snapshot.get('asset_id'):
        return payload
    row = owned(db, user, snapshot['template_id'])
    media_id = sending_media(row, snapshot['asset_id'], connection, snapshot['definition']['header_type'])
    result = copy.deepcopy(payload)
    header = next(p for p in result['components'] if p['type'] == 'header')
    kind = snapshot['definition']['header_type'].lower()
    header['parameters'][0][kind] = {'id': media_id}
    return result


def verify_queued(db, user, snapshot, connection):
    """Verify the retained version, including versions superseded locally."""
    row = owned(db, user, snapshot['template_id'])
    definition = snapshot['definition']
    if definition.get('waba_id') != connection.whatsapp_waba_id:
        raise HTTPException(409, 'Queued template belongs to another WABA')
    current = approved_definition(row) or {}
    if definition.get('meta_id') == current.get('meta_id'):
        if not row.is_active or (row.stats or {}).get('meta_status') != 'APPROVED':
            raise HTTPException(409, 'Queued template is no longer approved')
    else:
        historical = next((d for d in (row.workflow or {}).get('approved_history', []) if d.get('meta_id') == definition.get('meta_id')), None)
        if not historical:
            raise HTTPException(409, 'Queued approved version is unavailable; recreate the campaign')
        status = graph(definition['meta_id'], connection.whatsapp_access_token, params={'fields': 'id,status'})
        if status.get('status') != 'APPROVED':
            raise HTTPException(409, 'Queued historical version is no longer approved by Meta')
    return row
