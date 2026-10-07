import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.database.connection import get_db
from app.models import User, WhatsAppConnection, WhatsAppSignupAttempt
from app.services.security import require_owner, require_organization, tenant_id_for_user
from app.services.whatsapp_connections import (
    authorized_assets, decrypt_token, encrypt_token, get_connection, graph,
    public_connection, require_signup_configuration,
)

router = APIRouter()


class ExchangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: str = Field(min_length=20, max_length=80)
    code: str = Field(min_length=1, max_length=4096)


class SelectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: str = Field(min_length=20, max_length=80)
    waba_id: str = Field(pattern=r"^\d{1,80}$")
    phone_number_id: str = Field(pattern=r"^\d{1,80}$")
    registration_pin: str | None = Field(default=None, pattern=r"^\d{6}$")


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def attempt_for(db, user, state, phase):
    attempt = db.scalar(select(WhatsAppSignupAttempt).where(
        WhatsAppSignupAttempt.id == state,
        WhatsAppSignupAttempt.tenant_id == tenant_id_for_user(user),
        WhatsAppSignupAttempt.organization_id == user.organization_id,
        WhatsAppSignupAttempt.user_id == user.id,
    ).with_for_update())
    if not attempt or attempt.expires_at <= now() or attempt.phase != phase:
        raise HTTPException(400, "This WhatsApp connection attempt has expired or was already used. Start again")
    return attempt


@router.get("/")
def status(user: User = Depends(require_organization), db: Session = Depends(get_db)):
    settings = get_settings()
    configured = bool(settings.meta_app_id and settings.whatsapp_signup_config_id and settings.meta_app_secret and settings.whatsapp_token_encryption_key)
    return {"success": True, "data": {**public_connection(get_connection(db, user)),
        "signup_configured": configured, "can_manage": user.role == "owner" and user.organization.owner_id == user.id}}


@router.post("/start")
def start(user: User = Depends(require_owner), db: Session = Depends(get_db)):
    settings = require_signup_configuration()
    db.execute(delete(WhatsAppSignupAttempt).where(WhatsAppSignupAttempt.expires_at <= now()))
    attempt = WhatsAppSignupAttempt(id=secrets.token_urlsafe(32), tenant_id=tenant_id_for_user(user),
        organization_id=user.organization_id, user_id=user.id, expires_at=now() + timedelta(minutes=10), phase="started")
    db.add(attempt)
    db.commit()
    return {"success": True, "data": {"state": attempt.id, "app_id": settings.meta_app_id,
        "config_id": settings.whatsapp_signup_config_id, "graph_version": settings.whatsapp_graph_version}}


@router.post("/exchange")
def exchange(payload: ExchangeRequest, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    settings = require_signup_configuration()
    attempt = attempt_for(db, user, payload.state, "started")
    # Consume before contacting Meta. A failed exchange requires a new attempt.
    attempt.phase = "exchanging"
    db.commit()
    result = graph("oauth/access_token", params={"client_id": settings.meta_app_id,
        "client_secret": settings.meta_app_secret, "code": payload.code})
    token = result.get("access_token")
    if not token or not isinstance(token, str):
        raise HTTPException(502, "Meta did not return an authorization token")
    assets, expires_at = authorized_assets(token)
    # Recheck expiry after network calls; do not revive an expired attempt.
    attempt = attempt_for(db, user, payload.state, "exchanging")
    attempt.encrypted_access_token = encrypt_token(token, attempt.tenant_id, attempt.organization_id)
    attempt.token_expires_at = expires_at
    attempt.phase = "selecting"
    db.commit()
    return {"success": True, "data": {"assets": assets}}


@router.post("/select")
def select_phone(payload: SelectRequest, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    require_signup_configuration()
    attempt = attempt_for(db, user, payload.state, "selecting")
    token = decrypt_token(attempt.encrypted_access_token, attempt.tenant_id, attempt.organization_id)
    assets, expires_at = authorized_assets(token)
    asset = next((a for a in assets if a["waba_id"] == payload.waba_id and a["phone_number_id"] == payload.phone_number_id), None)
    if not asset:
        raise HTTPException(403, "Meta has not authorized this phone number for the current connection attempt")
    connection = db.scalar(select(WhatsAppConnection).where(
        WhatsAppConnection.organization_id == user.organization_id,
        WhatsAppConnection.tenant_id == tenant_id_for_user(user),
    ).with_for_update())
    if not connection:
        connection = WhatsAppConnection(tenant_id=tenant_id_for_user(user), organization_id=user.organization_id)
        db.add(connection)
    connection.waba_id = asset["waba_id"]
    connection.phone_number_id = asset["phone_number_id"]
    connection.display_phone_number = asset["display_phone_number"]
    connection.verified_name = asset["verified_name"]
    connection.encrypted_access_token = encrypt_token(token, connection.tenant_id, connection.organization_id)
    connection.connected_by = user.id
    connection.token_expires_at = expires_at
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "This sender is already connected to another organization") from None
    if payload.registration_pin:
        registered = graph(asset["phone_number_id"] + "/register", token, method="POST",
            data={"messaging_product": "whatsapp", "pin": payload.registration_pin})
        if registered.get("success") is not True:
            raise HTTPException(502, "Meta did not confirm phone registration")
    subscribed = graph(asset["waba_id"] + "/subscribed_apps", token, method="POST")
    if subscribed.get("success") is not True:
        raise HTTPException(502, "Meta did not confirm the webhook subscription")
    attempt.phase = "completed"
    attempt.encrypted_access_token = None
    db.commit()
    return {"success": True, "data": public_connection(connection)}


@router.delete("/")
def disconnect(user: User = Depends(require_owner), db: Session = Depends(get_db)):
    connection = get_connection(db, user)
    if connection:
        db.delete(connection)
    db.execute(delete(WhatsAppSignupAttempt).where(
        WhatsAppSignupAttempt.organization_id == user.organization_id,
        WhatsAppSignupAttempt.tenant_id == tenant_id_for_user(user),
    ))
    db.commit()
    return {"success": True, "message": "Disconnected from this CRM. No WhatsApp account or Meta assets were deleted"}
