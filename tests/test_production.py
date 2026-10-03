from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException

from app.config.settings import Settings, get_settings
from app.models import User
from app.services.security import create_token, decode_token, hash_password, verify_password
from app.utils.helpers import model_to_dict


def test_password_is_salted_and_verifiable():
    first = hash_password("valid-password")
    assert first != hash_password("valid-password")
    assert first != "valid-password"
    assert verify_password("valid-password", first)
    assert not verify_password("incorrect", first)


@pytest.mark.parametrize("password", ["", "a" * 73, "\u00e9" * 37], ids=["empty", "ascii-too-long", "utf8-too-long"])
def test_invalid_password_rejected(password):
    with pytest.raises(HTTPException) as error:
        hash_password(password)
    assert error.value.status_code == 400


def test_password_at_utf8_byte_limit():
    password = "\u00e9" * 36
    assert verify_password(password, hash_password(password))


def test_legacy_password_remains_verifiable():
    assert verify_password("legacy", "legacy")
    assert not verify_password("incorrect", "legacy")


def test_token_roundtrip():
    payload = {"userId": 17, "tenantId": 4}
    decoded = decode_token(create_token(payload))
    assert decoded is not None
    assert decoded["userId"] == 17 and decoded["tenantId"] == 4
    assert "exp" not in payload


@pytest.mark.parametrize("case", ["expired", "wrong-secret", "invalid"])
def test_untrusted_token_rejected(case):
    settings = get_settings()
    if case == "invalid":
        token = "not-a-token"
    else:
        expiration = datetime.now(timezone.utc) + timedelta(minutes=-1 if case == "expired" else 10)
        secret = settings.jwt_secret if case == "expired" else "different-test-secret-at-least-32-characters"
        token = jwt.encode({"userId": 1, "exp": expiration}, secret, algorithm="HS256")
    assert decode_token(token) is None


@pytest.mark.parametrize("secret", ["supersecretkey", "short", ""])
def test_production_rejects_weak_secret(monkeypatch, secret):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", secret)
    with pytest.raises(ValueError, match="JWT_SECRET"):
        Settings()


def test_production_requires_database_url(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("DATABASE_URL")
    with pytest.raises(ValueError, match="DATABASE_URL"):
        Settings()


def test_api_serialization_excludes_credentials():
    user = User(id=1, email="user@example.com", password="secret", phone_otp_hash="otp", password_reset_token="reset")
    data = model_to_dict(user)
    assert data["email"] == "user@example.com"
    assert not {"password", "phone_otp_hash", "phoneOtpHash", "password_reset_token", "passwordResetToken"} & data.keys()
