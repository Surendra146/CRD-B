import pytest
from sqlalchemy import select

from app.models import User
from app.services.security import create_token, verify_password

pytestmark = pytest.mark.integration


def test_health_and_startup(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"success": True, "status": "ok"}


def test_register_persists_hash_and_login_authenticates(client, account, db_session):
    user = db_session.scalar(select(User).where(User.email == account["payload"]["email"]))
    assert user is not None
    assert user.password != account["payload"]["password"]
    assert verify_password(account["payload"]["password"], user.password)
    response = client.post("/api/auth/login", json=account["payload"])
    assert response.status_code == 200
    assert "password" not in response.json()["data"]
    profile = client.get("/api/auth/me", headers=account["headers"])
    assert profile.status_code == 200
    assert profile.json()["data"]["email"] == account["payload"]["email"]


def test_duplicate_registration_rejected(client, account):
    assert client.post("/api/auth/register", json=account["payload"]).status_code == 409


def test_production_login_sets_secure_cookie(client, account, monkeypatch):
    from app.config.settings import get_settings
    monkeypatch.setenv("ENVIRONMENT", "production")
    get_settings.cache_clear()
    response = client.post("/api/auth/login", json=account["payload"])
    assert response.status_code == 200
    assert "Secure" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]


@pytest.mark.parametrize("token", [None, "invalid-token"])
def test_profile_requires_valid_authentication(client, token):
    headers = {"Authorization": "Bearer " + token} if token else {}
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_incorrect_password_rejected(client, account):
    assert client.post("/api/auth/login", json={**account["payload"], "password": "wrong"}).status_code == 401


def test_legacy_password_upgraded_on_login(client, account, db_session):
    user = db_session.get(User, account["user"]["id"])
    user.password = account["payload"]["password"]
    db_session.commit()
    assert client.post("/api/auth/login", json=account["payload"]).status_code == 200
    db_session.refresh(user)
    assert user.password.startswith("$2b$")
    assert verify_password(account["payload"]["password"], user.password)


def test_inactive_user_cannot_access_profile(client, account, db_session):
    user = db_session.get(User, account["user"]["id"])
    user.is_active = False
    db_session.commit()
    assert client.get("/api/auth/me", headers=account["headers"]).status_code == 401


def test_token_tenant_mismatch_rejected(client, account):
    token = create_token({"userId": account["user"]["id"], "tenantId": account["user"]["tenantId"] + 999})
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer " + token}).status_code == 401


def test_reset_without_verified_token_cannot_change_password(client, account, db_session):
    user = db_session.get(User, account["user"]["id"])
    before = user.password
    response = client.post("/api/auth/reset-password", json={"email": user.email, "password": "changed"})
    assert response.status_code == 501
    db_session.refresh(user)
    assert user.password == before


def test_change_password_requires_current_password(client, account):
    headers = account["headers"]
    assert client.put("/api/auth/password", headers=headers, json={"currentPassword": "wrong", "newPassword": "New-password-123!"}).status_code == 400
    assert client.put("/api/auth/password", headers=headers, json={"currentPassword": account["payload"]["password"], "newPassword": "New-password-123!"}).status_code == 200
    assert client.post("/api/auth/login", json=account["payload"]).status_code == 401
    assert client.post("/api/auth/login", json={**account["payload"], "password": "New-password-123!"}).status_code == 200


@pytest.mark.parametrize("origin,expected", [("https://frontend.example.com", 200), ("https://untrusted.onrender.com", 400)])
def test_cors_only_allows_configured_origins(client, origin, expected):
    response = client.options("/api/auth/me", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})
    assert response.status_code == expected
    assert (response.headers.get("access-control-allow-origin") == origin) == (expected == 200)


def test_registration_validation(client):
    assert client.post("/api/auth/register", json={"email": "user@example.com"}).status_code == 422
