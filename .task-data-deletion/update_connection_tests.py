from pathlib import Path
root = Path(__file__).resolve().parents[1]
path = root / 'tests/test_whatsapp_delivery.py'
s = path.read_text()
s = s.replace('    monkeypatch.setattr(webhooks, "get_settings", lambda: settings)', '    monkeypatch.setattr(webhooks, "get_settings", lambda: settings)\n    monkeypatch.setattr(communications, "resolve_credentials", lambda db, user: settings)')
s = s.replace('communications.send_whatsapp(CommunicationRequest(phone="8341645455", message="Hello"))', 'communications.send_whatsapp(CommunicationRequest(phone="8341645455", message="Hello"), SimpleNamespace(), object())')
s = s.replace('meta.send_message("8341645455", "Hello")', 'meta.send_message("8341645455", "Hello", connection=settings)')
s = s.replace('assert error.value.status_code == 503', 'assert error.value.status_code == 409')
s = s.replace('        def scalars(self, query): return self', '        def scalar(self, query): return SimpleNamespace(tenant_id=1, organization_id=1, phone_number_id="123", waba_id="999")\n        def scalars(self, query): return self')
s = s.replace('"entry": [{"changes":', '"entry": [{"id": "999", "changes":')
path.write_text(s)
path = root / 'tests/test_security_audit.py'
s = path.read_text()
start = s.index('def test_production_sender_is_not_shared_with_unapproved_tenants(')
end = s.index('\ndef test_live_directory', start)
s = s[:start] + '''def test_sending_requires_whatsapp_permission():
    with pytest.raises(HTTPException) as error:
        require_whatsapp_access(SimpleNamespace(organization_id=2, role="member", allowed_modules=[]))
    assert error.value.status_code == 403
    owner = SimpleNamespace(organization_id=2, role="owner")
    assert require_whatsapp_access(owner) is owner


''' + s[end:]
path.write_text(s)
path = root / 'tests/integration/test_whatsapp_api.py'
s = path.read_text()
s = s.replace('def test_dispatch_then_webhook_updates_persisted_job(client, account, monkeypatch):', 'def test_dispatch_then_webhook_updates_persisted_job(client, account, monkeypatch, db_session):')
before = '    monkeypatch.setattr(settings, "meta_app_secret", "test-app-secret")'
after = before + '''
    from cryptography.fernet import Fernet
    from app.models import WhatsAppConnection
    from app.services.whatsapp_connections import encrypt_token
    monkeypatch.setattr(settings, "whatsapp_token_encryption_key", Fernet.generate_key().decode())
    tenant_id = account["user"]["tenant_id"]
    org_id = account["user"]["organization_id"]
    db_session.add(WhatsAppConnection(tenant_id=tenant_id, organization_id=org_id, waba_id="999", phone_number_id="123", encrypted_access_token=encrypt_token("test-token", tenant_id, org_id), connected_by=account["user"]["id"]))
    db_session.commit()
'''
s = s.replace(before, after).replace('"entry": [{"changes":', '"entry": [{"id": "999", "changes":')
path.write_text(s)
