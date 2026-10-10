"""Tenant-scoped secrets and Meta-verified Embedded Signup assets."""
import hashlib
import base64
import hmac
import json
import re
from datetime import datetime, timezone
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy import select

from app.config.settings import get_settings
from app.models import WhatsAppConnection
from app.services.security import tenant_id_for_user
from app.services.meta_whatsapp import urlopen


def cipher():
    key = get_settings().whatsapp_token_encryption_key
    if not key:
        raise HTTPException(503, "WhatsApp connection encryption is not configured by the service administrator")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError):
        if len(key) < 32:
            raise HTTPException(503, "WhatsApp encryption requires a randomly generated key of at least 32 characters") from None
        # Render's generated secrets need not use Fernet's base64 format.
        return Fernet(base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest()))


def encrypt_token(token, tenant_id, organization_id):
    value = json.dumps({"token": token, "tenant": tenant_id, "organization": organization_id}).encode()
    return cipher().encrypt(value).decode()


def decrypt_token(value, tenant_id, organization_id):
    try:
        payload = json.loads(cipher().decrypt(value.encode()))
        if payload["tenant"] != tenant_id or payload["organization"] != organization_id:
            raise InvalidToken
        return payload["token"]
    except (InvalidToken, ValueError, KeyError, TypeError):
        raise HTTPException(503, "The WhatsApp connection cannot be decrypted. Contact the service administrator") from None


def get_connection(db, user, phone_number_id=None):
    statement = select(WhatsAppConnection).where(WhatsAppConnection.tenant_id == tenant_id_for_user(user),
        WhatsAppConnection.organization_id == user.organization_id)
    if phone_number_id:
        statement = statement.where(WhatsAppConnection.phone_number_id == phone_number_id)
    return db.scalar(statement.order_by(WhatsAppConnection.is_default.desc(), WhatsAppConnection.id.asc()).limit(1))


def resolve_credentials(db, user, phone_number_id=None):
    connection = get_connection(db, user, phone_number_id) if phone_number_id else get_connection(db, user)
    if not connection:
        raise HTTPException(409, "Connect your organization's WhatsApp Business account in Settings first")
    if connection.token_expires_at and connection.token_expires_at <= datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(409, "Your WhatsApp connection has expired. Reconnect it in Settings")
    return SimpleNamespace(
        whatsapp_provider="meta_cloud",
        whatsapp_graph_version=get_settings().whatsapp_graph_version,
        whatsapp_phone_number_id=connection.phone_number_id,
        whatsapp_waba_id=getattr(connection, "waba_id", None),
        whatsapp_access_token=decrypt_token(connection.encrypted_access_token, connection.tenant_id, connection.organization_id),
    )


def public_connection(connection):
    if not connection:
        return {"connected": False}
    expired = bool(connection.token_expires_at and connection.token_expires_at <= datetime.now(timezone.utc).replace(tzinfo=None))
    return {
        "connected": not expired, "expired": expired, "is_default": getattr(connection, "is_default", False),
        "waba_id": connection.waba_id, "phone_number_id": connection.phone_number_id,
        "display_phone_number": connection.display_phone_number,
        "verified_name": connection.verified_name,
        "token_expires_at": connection.token_expires_at.isoformat() if connection.token_expires_at else None,
    }


def require_signup_configuration():
    settings = get_settings()
    cipher()
    if not settings.meta_app_secret or not re.fullmatch(r"\d+", settings.meta_app_id) or not re.fullmatch(r"\d+", settings.whatsapp_signup_config_id):
        raise HTTPException(503, "Meta Embedded Signup is not configured by the service administrator")
    if not re.fullmatch(r"v\d+\.\d+", settings.whatsapp_graph_version):
        raise HTTPException(503, "Invalid Meta Graph API version")
    return settings


def graph(path, token=None, *, params=None, method="GET", data=None):
    settings = get_settings()
    if not re.fullmatch(r"(?:\d+(?:/[a-z_]+)?|oauth/access_token|debug_token)", path):
        raise HTTPException(400, "Invalid Meta request path")
    url = f"https://graph.facebook.com/{settings.whatsapp_graph_version}/{path}"
    query = dict(params or {})
    if token and settings.meta_app_secret:
        query["appsecret_proof"] = hmac.new(settings.meta_app_secret.encode(), token.encode(), hashlib.sha256).hexdigest()
    if query:
        url += "?" + urlencode(query)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(url, data=json.dumps(data or {}).encode() if method != "GET" else None, headers=headers, method=method)
    try:
        with urlopen(request, timeout=20) as response:
            result = json.loads(response.read(2_000_000))
    except HTTPError as error:
        try:
            code = json.loads(error.read()).get("error", {}).get("code")
        except (ValueError, AttributeError):
            code = None
        raise HTTPException(502, {"message": "Meta could not complete the connection request. Check account permissions and setup", "code": code}) from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise HTTPException(502, "Meta could not confirm the connection request. Start a new connection attempt") from None
    if not isinstance(result, dict):
        raise HTTPException(502, "Unexpected Meta response")
    return result


def authorized_assets(token):
    settings = require_signup_configuration()
    debug = graph("debug_token", settings.meta_app_id + "|" + settings.meta_app_secret, params={"input_token": token}).get("data", {})
    if not debug.get("is_valid") or str(debug.get("app_id")) != settings.meta_app_id:
        raise HTTPException(400, "The Meta authorization is invalid or belongs to another application")
    if not {"whatsapp_business_management", "whatsapp_business_messaging"}.issubset(set(debug.get("scopes") or [])):
        raise HTTPException(400, "Meta did not grant both WhatsApp management and messaging permissions")
    expiry = int(debug.get("expires_at") or 0)
    data_expiry = int(debug.get("data_access_expires_at") or 0)
    expiries = [n for n in (expiry, data_expiry) if n]
    expires_at = datetime.fromtimestamp(min(expiries), timezone.utc).replace(tzinfo=None) if expiries else None
    if expires_at and expires_at <= datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(400, "Meta authorization has expired")
    wabas = {str(identifier) for scope in debug.get("granular_scopes", [])
             if scope.get("scope") == "whatsapp_business_management" for identifier in scope.get("target_ids", [])}
    assets = []
    for waba in sorted(wabas)[:20]:
        if not re.fullmatch(r"\d+", waba):
            continue
        response = graph(waba + "/phone_numbers", token, params={"fields": "id,display_phone_number,verified_name", "limit": 100})
        for phone in response.get("data", []):
            assets.append({"waba_id": waba, "phone_number_id": str(phone["id"]),
                           "display_phone_number": phone.get("display_phone_number"), "verified_name": phone.get("verified_name")})
    if not assets:
        raise HTTPException(400, "Meta did not grant access to a WhatsApp business phone number. Complete Embedded Signup and try again")
    return assets, expires_at
