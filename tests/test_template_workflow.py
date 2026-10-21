import copy
import io
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from PIL import Image

from app.services.template_definitions import compile_draft, outgoing, provider_definition
from app.services.template_media import validate_media, store_asset, asset, sample_handle, sending_media
from app.services.template_workflow import merge_provider, prepare_send, submit, refresh


def draft():
    return {'language': 'en_US', 'header': {'type': 'TEXT', 'text': 'Welcome {{name}}'},
            'body': 'Hi {{name}}, your order for {{name}} is ready.', 'footer': 'Thank you',
            'buttons': [{'type': 'URL', 'text': 'Order', 'url': 'https://example.com/{{phone}}'},
                        {'type': 'PHONE_NUMBER', 'text': 'Call', 'phone_number': '+919876543210'},
                        {'type': 'QUICK_REPLY', 'text': 'Thanks'}],
            'mappings': {'header': {'name': 'customer.name'}, 'body': {'name': 'customer.name'}, 'button_0': {'phone': 'customer.phone'}},
            'examples': {'header': {'name': 'Alice'}, 'body': {'name': 'Alice'}, 'button_0': {'phone': '12345'}}}


def row():
    return SimpleNamespace(id=1, tenant_id=7, organization_id=8, category='MARKETING',
        name='Welcome', whatsapp_template_name='welcome', content=draft(), workflow={}, stats={}, targeting={}, is_active=True)


def png():
    buffer = io.BytesIO()
    Image.new('RGB', (10, 10)).save(buffer, 'PNG')
    return buffer.getvalue()


def definition():
    return compile_draft('welcome', 'MARKETING', draft())


def test_deterministic_repeated_component_variables_and_exact_payload():
    d = definition()
    assert d['components'][1]['text'] == 'Hi {{1}}, your order for {{1}} is ready.'
    assert d['components'][1]['example'] == {'body_text': [['Alice']]}
    assert d['components'][3]['buttons'][0]['example'] == ['https://example.com/12345']
    assert outgoing(d, {'name': 'Bob', 'phone': '456'}) == {'name': 'welcome', 'language': {'code': 'en_US'}, 'components': [
        {'type': 'header', 'parameters': [{'type': 'text', 'text': 'Bob'}]},
        {'type': 'body', 'parameters': [{'type': 'text', 'text': 'Bob'}]},
        {'type': 'button', 'sub_type': 'url', 'index': '0', 'parameters': [{'type': 'text', 'text': '456'}]}]}
    assert outgoing(d, {'name': 'Carol', 'phone': '789'})['components'][1]['parameters'][0]['text'] == 'Carol'


@pytest.mark.parametrize('change', [
    lambda c: c.update(body='{{name}}'),
    lambda c: c.update(footer='{{name}}'),
    lambda c: c['header'].update(type='LOCATION'),
    lambda c: c['examples']['body'].clear(),
    lambda c: c['mappings']['body'].update(name='customer.password'),
    lambda c: c['buttons'][0].update(url='javascript:alert(1)'),
    lambda c: c['buttons'][1].update(phone_number='555'),
    lambda c: c['buttons'][0].update(type='FLOW'),
    lambda c: c['buttons'][0].update(text='x' * 26),
    lambda c: c.update(body='Hi {{2}} there'),
])
def test_submission_validation(change):
    c = draft(); change(c)
    with pytest.raises(HTTPException):
        compile_draft('welcome', 'UTILITY', c)


def test_unresolved_recipient_never_sent():
    with pytest.raises(HTTPException):
        outgoing(definition(), {'phone': '456'})


@pytest.mark.parametrize('kind', ['IMAGE', 'VIDEO', 'DOCUMENT'])
def test_media_header_exact_outgoing(kind):
    c = draft(); c['header'] = {'type': kind, 'asset_id': 'owned'}
    d = compile_draft('welcome', 'UTILITY', c)
    with pytest.raises(HTTPException):
        outgoing(d, {'name': 'Bob', 'phone': '456'})
    assert outgoing(d, {'name': 'Bob', 'phone': '456'}, '123')['components'][0] == {
        'type': 'header', 'parameters': [{'type': kind.lower(), kind.lower(): {'id': '123'}}]}


def test_media_detection_ignores_extension_and_rejects_spoofed_mime():
    assert validate_media(png(), 'image/png') == ('image', 'image/png')
    for content, mime in [(png(), 'application/pdf'), (b'bad', 'image/png'), (b'%PDF-fake', 'application/pdf'), (b'', None)]:
        with pytest.raises(HTTPException): validate_media(content, mime)


def test_media_limits(monkeypatch):
    from app.services import template_media
    monkeypatch.setitem(template_media.LIMITS, 'image', 1)
    with pytest.raises(HTTPException) as error: validate_media(png(), 'image/png')
    assert error.value.status_code == 413


def test_valid_pdf():
    from reportlab.pdfgen.canvas import Canvas
    buffer = io.BytesIO(); canvas = Canvas(buffer); canvas.drawString(10, 10, 'sample'); canvas.save()
    assert validate_media(buffer.getvalue(), 'application/pdf') == ('document', 'application/pdf')


def test_invalid_mp4_and_missing_validator(monkeypatch):
    import subprocess
    def fail(*a, **kw): raise FileNotFoundError()
    monkeypatch.setattr(subprocess, 'run', fail)
    with pytest.raises(HTTPException) as e: validate_media(b'\0\0\0\x18ftypisom' + b'\0' * 16, 'video/mp4')
    assert e.value.status_code == 503


def test_asset_ownership_missing_and_corrupt(tmp_path, monkeypatch):
    monkeypatch.setenv('WHATSAPP_TEMPLATE_MEDIA_ROOT', str(tmp_path))
    r = row(); entry = store_asset(r, png(), 'image/png', '../../unsafe.png')
    assert entry['name'] == 'unsafe.png'
    assert asset(r, entry['id'])[1] == png()
    other = row(); other.organization_id = 999
    with pytest.raises(HTTPException): asset(other, entry['id'])
    other.workflow = copy.deepcopy(r.workflow)
    with pytest.raises(HTTPException): asset(other, entry['id'])
    with pytest.raises(HTTPException): asset(r, entry['id'], 'DOCUMENT')
    with pytest.raises(HTTPException): asset(r, '../../secret')
    from app.services.template_media import asset_path
    asset_path(r, entry['id']).write_bytes(b'changed')
    with pytest.raises(HTTPException): asset(r, entry['id'])


def test_sample_handle_and_message_media_id_are_separate(tmp_path, monkeypatch):
    from app.services import template_media
    monkeypatch.setenv('WHATSAPP_TEMPLATE_MEDIA_ROOT', str(tmp_path))
    monkeypatch.setattr(template_media, 'get_settings', lambda: SimpleNamespace(meta_app_id='123'))
    upload = Mock(side_effect=[{'id': 'upload:session'}, {'h': 'sample-only'}, {'id': '456'}])
    monkeypatch.setattr(template_media, 'provider_upload', upload)
    r = row(); entry = store_asset(r, png(), 'image/png', 'test.png')
    connection = SimpleNamespace(whatsapp_phone_number_id='789', whatsapp_access_token='test-token')
    assert sample_handle(r, entry['id'], connection) == 'sample-only'
    assert sending_media(r, entry['id'], connection, 'IMAGE') == '456'
    assert upload.call_args_list[1].args[1] == 'upload:session'
    assert upload.call_args_list[2].args[1] == '789/media'


def test_approval_merge_preserves_draft_mappings_and_rejection():
    r = row(); before = copy.deepcopy(r.content); d = definition(); d['meta_id'] = '123'
    r.workflow = {'submitted': d, 'submitted_at': '2026-10-17T00:00:00', 'draft_revision': 3}
    item = {**d, 'id': '123', 'status': 'APPROVED'}
    assert merge_provider(r, item, '55', '66')
    assert r.content == before
    assert r.workflow['approved']['parameters'] == d['parameters']
    r.content['body'] = 'New draft'
    assert r.workflow['approved']['components'][1]['text'].startswith('Hi {{1}}')
    merge_provider(r, {**item, 'status': 'REJECTED', 'rejected_reason': 'Policy'}, '55', '66')
    assert r.workflow['rejection_reason'] == 'Policy'
    assert not r.is_active


def test_stale_sync_cannot_overwrite_submission():
    r = row(); r.workflow = {'submitted_at': '2026-10-17T12:00:00', 'status': 'PENDING'}
    assert not merge_provider(r, {**definition(), 'id': '123', 'status': 'APPROVED'}, '55', '66', '2026-10-17T11:00:00')
    assert r.workflow['status'] == 'PENDING'


def test_external_media_template_needs_mappings_not_sample():
    d = provider_definition({'id': '123', 'name': 'external', 'language': 'en_US', 'category': 'UTILITY',
        'components': [{'type': 'HEADER', 'format': 'IMAGE'}, {'type': 'BODY', 'text': 'Hi {{1}} there'}]})
    with pytest.raises(HTTPException): outgoing(d, {'name': 'Bob'}, '456')
    result = outgoing(d, {'name': 'Bob'}, '456', {'body': ['name']})
    assert result['components'][1]['parameters'][0]['text'] == 'Bob'


@pytest.mark.parametrize('status,waba,org', [('PENDING', '55', 8), ('APPROVED', '99', 8), ('APPROVED', '55', 999)])
def test_unapproved_mismatched_and_cross_org_sends_blocked(status, waba, org):
    r = row(); r.organization_id = org
    d = definition(); d['waba_id'] = '55'
    r.workflow = {'approved': d}; r.stats = {'meta_status': status}
    db = Mock(); db.scalar.return_value = r
    user = SimpleNamespace(tenant_id=7, organization_id=8)
    with pytest.raises(HTTPException): prepare_send(db, user, {'template': {'id': 1}}, SimpleNamespace(whatsapp_waba_id=waba), {'name': 'Bob', 'phone': '456'})


def test_duplicate_submission_is_blocked_before_provider(monkeypatch):
    r = row(); r.workflow = {'status': 'PENDING'}
    db = Mock(); db.scalar.return_value = r
    with pytest.raises(HTTPException) as error: submit(db, SimpleNamespace(tenant_id=7, organization_id=8), 1)
    assert error.value.status_code == 409


def test_submission_success_failure_and_refresh(monkeypatch):
    from app.services import template_workflow as service
    r = row(); db = Mock(); db.scalar.return_value = r; db.scalars.return_value.all.return_value = []
    user = SimpleNamespace(tenant_id=7, organization_id=8)
    monkeypatch.setattr(service, 'resolve_credentials', lambda *a: SimpleNamespace(whatsapp_waba_id='55', whatsapp_phone_number_id='66', whatsapp_access_token='secret'))
    graph = Mock(return_value={'id': '123', 'status': 'PENDING'})
    monkeypatch.setattr(service, 'graph', graph)
    original = copy.deepcopy(r.content)
    submit(db, user, 1)
    assert r.workflow['submitted']['meta_id'] == '123' and r.content == original
    graph.return_value = {**r.workflow['submitted'], 'id': '123', 'status': 'APPROVED'}
    refresh(db, user, 1)
    assert r.workflow['approved']['name'] == 'welcome'
    r.content['body'] = 'Another draft'
    previous = copy.deepcopy(r.workflow['approved'])
    graph.side_effect = HTTPException(502, {'code': 100})
    with pytest.raises(HTTPException): submit(db, user, 1)
    assert r.workflow['status'] == 'SUBMISSION_FAILED'
    assert r.workflow['approved'] == previous and r.content['body'] == 'Another draft'
    graph.side_effect = HTTPException(502, 'timeout')
    with pytest.raises(HTTPException): submit(db, user, 1)
    assert r.workflow['status'] == 'SUBMISSION_UNKNOWN'
    with pytest.raises(HTTPException) as e: submit(db, user, 1)
    assert e.value.status_code == 409


def test_approved_duplicate_and_uncertain_retry_reuse_name(monkeypatch):
    from app.services import template_workflow as service
    from datetime import UTC, datetime, timedelta
    r = row(); db = Mock(); db.scalar.return_value = r; db.scalars.return_value.all.return_value = []
    user = SimpleNamespace(tenant_id=7, organization_id=8)
    monkeypatch.setattr(service, 'resolve_credentials', lambda *a: SimpleNamespace(whatsapp_waba_id='55', whatsapp_phone_number_id='66', whatsapp_access_token='secret'))
    graph = Mock(return_value={'id': '123', 'status': 'APPROVED'})
    monkeypatch.setattr(service, 'graph', graph)
    submit(db, user, 1)
    with pytest.raises(HTTPException) as duplicate: submit(db, user, 1)
    assert duplicate.value.status_code == 409 and graph.call_count == 1
    r.content['body'] = 'Changed content'
    graph.side_effect = HTTPException(502, 'timeout')
    with pytest.raises(HTTPException): submit(db, user, 1)
    reserved = r.workflow['submitted']['name']
    r.workflow['submitted_at'] = (datetime.now(UTC) - timedelta(minutes=6)).isoformat()
    graph.side_effect = None; graph.return_value = {'data': []}
    refresh(db, user, 1)
    assert r.workflow['status'] == 'SUBMISSION_NOT_FOUND'
    graph.return_value = {'id': '456', 'status': 'PENDING'}
    submit(db, user, 1)
    assert graph.call_args.kwargs['data']['name'] == reserved


def test_video_codec_validation(monkeypatch):
    import subprocess
    import json
    valid = {'streams': [{'codec_type': 'video', 'codec_name': 'h264'}, {'codec_type': 'audio', 'codec_name': 'aac'}]}
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: SimpleNamespace(stdout=json.dumps(valid).encode()))
    assert validate_media(b'\0\0\0\x18ftypisom' + b'\0' * 16, 'video/mp4') == ('video', 'video/mp4')
    valid['streams'][1]['codec_name'] = 'opus'
    with pytest.raises(HTTPException) as error: validate_media(b'\0\0\0\x18ftypisom' + b'\0' * 16, 'video/mp4')
    assert error.value.status_code == 422

@pytest.mark.parametrize('reason', [None, '', 'NONE', 'none', ' undefined ', 'null'])
def test_empty_rejection_reason(reason):
    from app.services.template_definitions import rejection_reason
    assert rejection_reason(reason) is None


def test_real_rejection_reason():
    from app.services.template_definitions import rejection_reason
    assert rejection_reason('Policy violation') == 'Policy violation'


def synced_row():
    r = row()
    d = definition()
    item = {**d, 'id': 'meta1', 'status': 'APPROVED', 'rejected_reason': 'NONE'}
    merge_provider(r, item, 'waba', 'sender')
    return r, item


def test_legacy_synced_baseline_ignores_revision_and_metadata():
    from app.services.template_definitions import has_unpublished_edits
    r, item = synced_row()
    r.workflow['draft_revision'] = 99
    assert r.workflow['rejection_reason'] is None
    assert not has_unpublished_edits(r)
    assert r.workflow['draft_baseline']
    item['components'].reverse()
    merge_provider(r, item, 'waba', 'sender')
    assert not has_unpublished_edits(r)


@pytest.mark.parametrize('change', [
    lambda c: c.update(body='A changed body'),
    lambda c: c['header'].update(text='A changed header'),
    lambda c: c['buttons'][0].update(text='Changed button'),
    lambda c: c.update(language='hi'),
    lambda c: c.update(meta_name='different_name'),
])
def test_real_drafts_survive_sync(change):
    from app.services.template_definitions import has_unpublished_edits
    r, item = synced_row()
    change(r.content)
    expected = copy.deepcopy(r.content)
    assert has_unpublished_edits(r)
    merge_provider(r, item, 'waba', 'sender')
    assert r.content == expected
    assert has_unpublished_edits(r)


def test_legacy_modified_content_is_not_baselined_away():
    from app.services.template_definitions import has_unpublished_edits
    r, item = synced_row()
    r.workflow.pop('draft_baseline')
    r.content['body'] = 'A real local change'
    merge_provider(r, item, 'waba', 'sender')
    assert has_unpublished_edits(r)
    assert 'draft_baseline' not in r.workflow


def test_media_compares_content_hash_not_internal_asset_id():
    from app.services.template_definitions import has_unpublished_edits
    r = row()
    r.content['header'] = {'type': 'IMAGE', 'asset_id': 'a'}
    r.workflow = {'assets': [{'id': 'a', 'sha256': 'same'}, {'id': 'b', 'sha256': 'same'}, {'id': 'c', 'sha256': 'changed'}]}
    item = {**compile_draft('welcome', r.category, r.content), 'id': 'meta1', 'status': 'APPROVED'}
    merge_provider(r, item, 'waba', 'sender')
    r.content['header']['asset_id'] = 'b'
    assert not has_unpublished_edits(r)
    r.content['header']['asset_id'] = 'c'
    assert has_unpublished_edits(r)

@pytest.mark.parametrize('edited', [False, True])
def test_refresh_recalculates_state_without_overwriting_draft(monkeypatch, edited):
    from app.services import template_workflow as service
    from app.services.template_definitions import has_unpublished_edits
    r, item = synced_row()
    if edited:
        r.content['body'] = 'Unsubmitted local message'
    original = copy.deepcopy(r.content)
    db = Mock(); db.scalar.return_value = r
    user = SimpleNamespace(tenant_id=7, organization_id=8)
    monkeypatch.setattr(service, 'resolve_credentials', lambda *a: SimpleNamespace(
        whatsapp_waba_id='waba', whatsapp_phone_number_id='sender', whatsapp_access_token='secret'))
    monkeypatch.setattr(service, 'graph', Mock(return_value=item))
    refresh(db, user, 1)
    assert r.content == original
    assert has_unpublished_edits(r) is edited
    assert r.workflow['rejection_reason'] is None


def test_rejected_sync_keeps_actual_reason():
    r, item = synced_row()
    item.update(status='REJECTED', rejected_reason='Policy violation')
    merge_provider(r, item, 'waba', 'sender')
    assert r.workflow['rejection_reason'] == 'Policy violation'


def test_generated_submission_name_is_not_a_local_edit(monkeypatch):
    from app.services import template_workflow as service
    from app.services.template_definitions import has_unpublished_edits
    r, item = synced_row()
    r.content['body'] = 'Updated body'
    db = Mock(); db.scalar.return_value = r; db.scalars.return_value.all.return_value = []
    monkeypatch.setattr(service, 'resolve_credentials', lambda *a: SimpleNamespace(
        whatsapp_waba_id='waba', whatsapp_phone_number_id='sender', whatsapp_access_token='secret'))
    graph = Mock(return_value={'id': 'new', 'status': 'PENDING'})
    monkeypatch.setattr(service, 'graph', graph)
    submit(db, SimpleNamespace(tenant_id=7, organization_id=8), 1)
    assert '_r' in r.workflow['submitted']['name']
    assert not has_unpublished_edits(r)
    item = {**r.workflow['submitted'], 'id': 'new', 'status': 'APPROVED'}
    merge_provider(r, item, 'waba', 'sender')
    assert not has_unpublished_edits(r)


def test_positional_variable_change_is_meaningful():
    from app.services.template_definitions import editable_signature
    first = editable_signature('a', 'UTILITY', {'body': 'Hi {{1}} and {{2}}'})
    swapped = editable_signature('a', 'UTILITY', {'body': 'Hi {{2}} and {{1}}'})
    assert first != swapped
