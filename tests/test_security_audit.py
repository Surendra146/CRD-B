import io
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.models import Customer
from app.services.crud import apply_payload
from app.services.security import require_owner, require_whatsapp_access
from app.services import security, gmaps_service, meta_whatsapp
from app.middlewares.request_limits import RequestLimitMiddleware
from app.services.whatsapp_service import filter_phone_numbers


@pytest.mark.parametrize("field", ["tenant_id", "organization_id", "id", "tenant_code", "created_at"])
def test_ownership_mass_assignment_blocked(field):
    customer = Customer(id=1, tenant_id=1, organization_id=1, name="Original")
    with pytest.raises(HTTPException) as error:
        apply_payload(customer, {"name": "Changed", field: 2})
    assert error.value.status_code == 400
    assert customer.name == "Original"


def test_member_cannot_manage_permissions():
    with pytest.raises(HTTPException) as error:
        require_owner(SimpleNamespace(role="member", id=2, organization=SimpleNamespace(owner_id=1)))
    assert error.value.status_code == 403


def test_owner_role_alone_cannot_impersonate_owner():
    with pytest.raises(HTTPException):
        require_owner(SimpleNamespace(role="owner", id=2, organization=SimpleNamespace(owner_id=1)))


def test_sending_requires_whatsapp_permission():
    with pytest.raises(HTTPException) as error:
        require_whatsapp_access(SimpleNamespace(organization_id=2, role="member", allowed_modules=[]))
    assert error.value.status_code == 403
    owner = SimpleNamespace(organization_id=2, role="owner")
    assert require_whatsapp_access(owner) is owner



def test_live_directory_never_invents_contact_information(monkeypatch):
    monkeypatch.setattr(gmaps_service.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(json.dumps([{"osm_id": 12, "name": "Actual business", "display_name": "Actual business, Hyderabad"}]).encode()))
    leads = gmaps_service.search_google_maps_leads("business", "Hyderabad", 20)
    assert len(leads) == 1
    assert leads[0]["phone"] is None
    assert leads[0]["rating"] is None
    assert leads[0]["website"] is None
    assert leads[0]["source"] == "OpenStreetMap"


def test_number_formatting_does_not_claim_whatsapp_registration():
    number = filter_phone_numbers(["9000000000"])["valid"][0]
    assert number["whatsapp_ready"] is None
    assert number["validation"] == "format_only"


def test_public_media_creates_real_meta_payload():
    payload = meta_whatsapp.build_message("9000000000", "Caption", media_files=[{"type": "image", "url": "https://example.com/product.jpg"}])
    assert payload["type"] == "image"
    assert payload["image"]["link"] == "https://example.com/product.jpg"


@pytest.mark.parametrize("url", ["blob:local", "http://example.com/a.jpg", "https://127.0.0.1/a.jpg", "https://localhost/a.jpg"])
def test_nonpublic_media_rejected(url):
    with pytest.raises(HTTPException):
        meta_whatsapp.build_message("9000000000", "Caption", media_files=[{"type": "image", "url": url}])


def test_request_size_limit_runs_before_handler():
    app = FastAPI()
    app.add_middleware(RequestLimitMiddleware, max_bytes=16)
    @app.post("/test")
    async def handler():
        pytest.fail("Oversized request reached handler")
    with TestClient(app) as client:
        assert client.post("/test", content=b"x" * 17).status_code == 413


def test_authentication_requests_are_rate_limited():
    from app.middlewares.auth_rate_limit import AuthRateLimitMiddleware
    app = FastAPI()
    app.add_middleware(AuthRateLimitMiddleware)
    @app.post("/api/auth/login")
    def login(): return {"ok": True}
    with TestClient(app) as client:
        for _ in range(30):
            assert client.post("/api/auth/login").status_code == 200
        assert client.post("/api/auth/login").status_code == 429
