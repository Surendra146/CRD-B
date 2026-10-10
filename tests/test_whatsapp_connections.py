import io
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from app.services import whatsapp_connections as connections, meta_whatsapp
from app.routers.whatsapp_connections import attempt_for, ExchangeRequest


@pytest.fixture
def config(monkeypatch):
    config = SimpleNamespace(whatsapp_token_encryption_key=Fernet.generate_key().decode(), meta_app_secret="private-secret", meta_app_id="111", whatsapp_signup_config_id="222", whatsapp_graph_version="v23.0")
    monkeypatch.setattr(connections, "get_settings", lambda: config)
    return config


def test_credentials_are_encrypted_and_bound_to_their_organization(config):
    encrypted = connections.encrypt_token("secret-tenant-token", 1, 2)
    assert "secret-tenant-token" not in encrypted
    assert connections.decrypt_token(encrypted, 1, 2) == "secret-tenant-token"
    with pytest.raises(HTTPException):
        connections.decrypt_token(encrypted, 1, 3)


def test_missing_encryption_key_never_stores_plaintext(config):
    config.whatsapp_token_encryption_key = ""
    with pytest.raises(HTTPException) as error:
        connections.encrypt_token("secret", 1, 2)
    assert error.value.status_code == 503


def test_missing_tenant_connection_never_uses_render_sender(config):
    class DB:
        def scalar(self, query): return None
    with pytest.raises(HTTPException) as error:
        connections.resolve_credentials(DB(), SimpleNamespace(tenant_id=1, organization_id=2))
    assert error.value.status_code == 409
    with pytest.raises(HTTPException):
        meta_whatsapp.send_message("9000000000", "Hello")


def test_resolver_uses_only_the_selected_tenant_credentials(config):
    row = SimpleNamespace(tenant_id=1, organization_id=2, phone_number_id="333", encrypted_access_token=connections.encrypt_token("tenant-token", 1, 2), token_expires_at=None)
    class DB:
        def scalar(self, query):
            params = query.compile().params
            assert params["tenant_id_1"] == 1
            assert params["organization_id_1"] == 2
            return row
    resolved = connections.resolve_credentials(DB(), SimpleNamespace(tenant_id=1, organization_id=2))
    assert resolved.whatsapp_phone_number_id == "333"
    assert resolved.whatsapp_access_token == "tenant-token"
    assert "tenant-token" not in json.dumps(connections.public_connection(SimpleNamespace(**row.__dict__, waba_id="444", display_phone_number="+919000000000", verified_name="Business")))


def test_expired_connection_requires_reauthorization(config):
    class DB:
        def scalar(self, query): return SimpleNamespace(token_expires_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1))
    with pytest.raises(HTTPException) as error:
        connections.resolve_credentials(DB(), SimpleNamespace(tenant_id=1, organization_id=2))
    assert error.value.status_code == 409


def test_meta_assets_are_discovered_and_verified_server_side(config, monkeypatch):
    def provider(request, timeout):
        if '/debug_token?' in request.full_url:
            assert request.get_header('Authorization') == 'Bearer 111|private-secret'
            response = {'data': {'is_valid': True, 'app_id': '111', 'scopes': ['whatsapp_business_management', 'whatsapp_business_messaging'], 'granular_scopes': [{'scope': 'whatsapp_business_management', 'target_ids': ['444']}]}}
        else:
            assert '/444/phone_numbers?' in request.full_url
            assert request.get_header('Authorization') == 'Bearer tenant-token'
            response = {'data': [{'id': '333', 'display_phone_number': '+919000000000', 'verified_name': 'Business'}]}
        return io.BytesIO(json.dumps(response).encode())
    monkeypatch.setattr(connections, 'urlopen', provider)
    assets, expiry = connections.authorized_assets('tenant-token')
    assert assets[0]['phone_number_id'] == '333'
    assert assets[0]['waba_id'] == '444'
    assert expiry is None


def test_another_meta_apps_token_is_rejected(config, monkeypatch):
    monkeypatch.setattr(connections, 'graph', lambda *args, **kwargs: {'data': {'is_valid': True, 'app_id': '999'}})
    with pytest.raises(HTTPException) as error:
        connections.authorized_assets('token')
    assert error.value.status_code == 400


def test_raw_access_tokens_cannot_be_submitted_as_oauth_payloads():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ExchangeRequest(state='a' * 32, code='code', access_token='untrusted-token')


def test_expired_signup_attempt_is_rejected():
    class DB:
        def scalar(self, query): return SimpleNamespace(expires_at=datetime.now(timezone.utc).replace(tzinfo=None)-timedelta(seconds=1), phase='started')
    with pytest.raises(HTTPException):
        attempt_for(DB(), SimpleNamespace(tenant_id=1, organization_id=2, id=3), 'nonce', 'started')
