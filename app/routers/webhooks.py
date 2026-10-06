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
from app.models import WhatsAppBulkJob
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
    if not secrets.compare_digest(request.headers.get("x-hub-signature-256", ""), expected):
        raise HTTPException(403, "Invalid webhook signature")
    try:
        payload = json.loads(body)
    except ValueError:
        raise HTTPException(400, "Invalid webhook JSON") from None
    if not isinstance(payload, dict) or payload.get("object") != "whatsapp_business_account":
        raise HTTPException(400, "Invalid WhatsApp webhook object")
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value") or {}
            if str(value.get("metadata", {}).get("phone_number_id")) != settings.whatsapp_phone_number_id:
                continue
            for status in value.get("statuses", []):
                message_id = status.get("id")
                if not message_id:
                    continue
                jobs = db.scalars(select(WhatsAppBulkJob).where(
                    WhatsAppBulkJob.recipients_summary.contains([{"message_id": message_id}])
                ).with_for_update()).all()
                for job in jobs:
                    job.recipients_summary = [
                        apply_status(rec, status) if rec.get("message_id") == message_id else rec
                        for rec in job.recipients_summary
                    ]
                    update_stats(job)
    db.commit()
    return {"success": True}
