import secrets
import hashlib
import hmac
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.database.connection import get_db
from app.models import WhatsAppBulkJob, WhatsAppConnection
from app.services.meta_whatsapp import apply_status, update_stats

router = APIRouter()


@router.get("/whatsapp", response_class=PlainTextResponse)
def verify_whatsapp(request: Request):
    expected_token = get_settings().whatsapp_verify_token
    if not expected_token:
        raise HTTPException(status_code=503, detail="WhatsApp verify token is not configured")

    mode = request.query_params.get("hub.mode")
    supplied_token = request.query_params.get("hub.verify_token", "")
    challenge = request.query_params.get("hub.challenge")
    if mode != "subscribe" or not secrets.compare_digest(
        supplied_token.encode("utf-8"), expected_token.encode("utf-8")
    ):
        raise HTTPException(status_code=403, detail="Webhook verification failed")
    if challenge is None or challenge == "":
        raise HTTPException(status_code=400, detail="Missing hub.challenge")
    return PlainTextResponse(challenge)


@router.post("/whatsapp")
async def receive_whatsapp(request: Request, db: Session = Depends(get_db)):
    settings = get_settings()
    if not settings.meta_app_secret:
        raise HTTPException(503, "META_APP_SECRET is required to verify WhatsApp webhooks")
    body = await request.body()
    expected = "sha256=" + hmac.new(settings.meta_app_secret.encode(), body, hashlib.sha256).hexdigest()
    if not secrets.compare_digest(request.headers.get("x-hub-signature-256", "").encode(), expected.encode()):
        raise HTTPException(403, "Invalid webhook signature")
    try:
        payload = json.loads(body)
    except ValueError:
        raise HTTPException(400, "Invalid webhook JSON") from None
    if not isinstance(payload, dict) or payload.get("object") != "whatsapp_business_account":
        raise HTTPException(400, "Invalid WhatsApp webhook object")
    entries = payload.get("entry", [])
    if not isinstance(entries, list):
        raise HTTPException(400, "Invalid webhook entries")
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("changes", []), list):
            raise HTTPException(400, "Invalid webhook changes")
        for change in entry.get("changes", []):
            if not isinstance(change, dict):
                raise HTTPException(400, "Invalid webhook change")
            value = change.get("value") or {}
            if not isinstance(value, dict) or not isinstance(value.get("metadata", {}), dict) or not isinstance(value.get("statuses", []), list):
                raise HTTPException(400, "Invalid webhook value")
            connection = db.scalar(select(WhatsAppConnection).where(
                WhatsAppConnection.phone_number_id == str(value.get("metadata", {}).get("phone_number_id", "")),
                WhatsAppConnection.waba_id == str(entry.get("id", "")),
            ))
            if not connection:
                continue
            for status in value.get("statuses", []):
                if not isinstance(status, dict):
                    raise HTTPException(400, "Invalid webhook status")
                message_id = status.get("id")
                if not message_id:
                    continue
                jobs = db.scalars(select(WhatsAppBulkJob).where(
                    WhatsAppBulkJob.recipients_summary.contains([{"message_id": message_id}]),
                    WhatsAppBulkJob.tenant_id == connection.tenant_id,
                    WhatsAppBulkJob.organization_id == connection.organization_id,
                    WhatsAppBulkJob.audience_payload["sender_phone_number_id"].as_string() == connection.phone_number_id,
                ).with_for_update()).all()
                for job in jobs:
                    job.recipients_summary = [
                        apply_status(rec, status) if rec.get("message_id") == message_id else rec
                        for rec in job.recipients_summary
                    ]
                    update_stats(job)
    db.commit()
    return {"success": True}
