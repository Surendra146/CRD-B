from datetime import datetime
from typing import Any
import time
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models import Customer, User, WhatsAppBulkJob
from app.schemas.communication import CommunicationRequest
from app.schemas.whatsapp_marketing import WhatsAppBulkSendRequest
from app.services.security import (
    ensure_tenant_access,
    require_organization,
    tenant_id_for_user,
    require_whatsapp_access,
)
from app.services.whatsapp_service import personalize_message
from app.services.meta_whatsapp import build_message, require_configuration, send_message, update_stats
from app.services.whatsapp_connections import get_connection, resolve_credentials, public_connection
from app.utils.helpers import model_to_dict


def communication_payload(payload: CommunicationRequest) -> dict:
    return payload.to_payload()


def send_whatsapp(payload: CommunicationRequest, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    payload_data = communication_payload(payload)
    result = send_message(
        payload_data.get("phone") or payload_data.get("to"), payload_data.get("message") or "",
        template=payload_data.get("template"), buttons=payload_data.get("buttons"),
        media_files=payload_data.get("media_files"),
        connection=resolve_credentials(db, user),
    )
    return {"success": True, "message": "Meta accepted the WhatsApp message; delivery is not yet confirmed", "data": result}


def send_whatsapp_message(payload: CommunicationRequest, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    return send_whatsapp(payload, user, db)


def send_communication(payload: CommunicationRequest, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    if payload.to_payload().get("channel", "whatsapp") != "whatsapp":
        raise HTTPException(400, "Only WhatsApp communication is supported")
    return send_whatsapp(payload, user, db)


router = APIRouter(dependencies=[Depends(require_whatsapp_access)])
configuration_router = APIRouter(dependencies=[Depends(require_organization)])

# Existing endpoints preserved with original behavior
router.post("/whatsapp")(send_whatsapp)
router.post("/whatsapp/send")(send_whatsapp_message)
router.post("/")(send_communication)


# =====================================================================
# BULK & SCHEDULED WHATSAPP MESSAGING
# =====================================================================
@router.post("/whatsapp/bulk")
def send_bulk_whatsapp(
    payload: WhatsAppBulkSendRequest,
    user: User = Depends(require_organization),
    db: Session = Depends(get_db),
):
    req = payload.to_payload()
    t_id = tenant_id_for_user(user)
    org_id = user.organization_id

    audience_type = req.get("audience_type") or req.get("audienceType") or "segment"
    audience = req.get("audience") or {}
    message_text = req.get("message") or ""
    buttons = req.get("buttons") or []
    media_files = req.get("media_files") or req.get("mediaFiles") or []
    batch_delay = int(req.get("batch_delay_seconds", req.get("batchDelaySeconds", 5)))
    if not 0 <= batch_delay <= 5:
        raise HTTPException(400, "Immediate broadcast delay must be between 0 and 5 seconds")
    scheduled_at_raw = req.get("scheduled_at") or req.get("scheduledAt")

    scheduled_at = None
    if scheduled_at_raw:
        raise HTTPException(400, "Automatic scheduled sending is not implemented. Choose Send Immediately")
    connection = resolve_credentials(db, user)
    require_configuration(connection)

    # Resolve target recipients
    recipients_data: list[dict[str, Any]] = []

    if audience_type == "segment":
        segment_id = audience.get("segmentId") or audience.get("segment") or ""
        stmt = select(Customer).where(
            Customer.tenant_id == t_id,
            Customer.organization_id == org_id,
            Customer.phone.is_not(None),
        )
        if segment_id and segment_id != "all":
            stmt = stmt.where(Customer.lifecycle["segment"].as_string() == segment_id)
        customers = db.scalars(stmt).all()
        for c in customers:
            recipients_data.append({
                "id": c.id,
                "name": c.name,
                "phone": c.phone,
                "email": c.email,
                "lifecycle": c.lifecycle or {},
                "demographics": c.demographics or {},
            })

    elif audience_type == "all":
        customers = db.scalars(
            select(Customer).where(
                Customer.tenant_id == t_id,
                Customer.organization_id == org_id,
                Customer.phone.is_not(None),
            )
        ).all()
        for c in customers:
            recipients_data.append({
                "id": c.id,
                "name": c.name,
                "phone": c.phone,
                "email": c.email,
                "lifecycle": c.lifecycle or {},
                "demographics": c.demographics or {},
            })

    elif audience_type in {"custom_numbers", "custom"}:
        raw_numbers = audience.get("numbers") or []
        for item in raw_numbers:
            if isinstance(item, dict):
                recipients_data.append({
                    "name": item.get("name") or "Recipient",
                    "phone": item.get("phone") or item.get("formatted"),
                })
            elif isinstance(item, str):
                recipients_data.append({
                    "name": f"Contact {item[-4:] if len(item) >= 4 else item}",
                    "phone": item,
                })

    if not recipients_data:
        raise HTTPException(400, "No reachable recipients found for the selected audience")
    if len(recipients_data) > 20:
        raise HTTPException(400, "Send up to 20 recipients per immediate broadcast until a durable background worker is configured")

    # Generate personalized messages for each recipient
    recipients_summary = []
    for rec in recipients_data:
        msg = personalize_message(message_text, rec)
        build_message(rec.get("phone"), msg, template=req.get("template"), buttons=buttons, media_files=media_files)
        recipients_summary.append({
            "name": rec.get("name"),
            "phone": rec.get("phone"),
            "personalized_message": msg,
            "status": "queued",
            "delivered_at": None,
        })

    job_status = "in_progress"
    total_count = len(recipients_summary)
    stats = {
        "total": total_count,
        "sent": 0,
        "failed": 0,
        "pending": total_count,
    }

    bulk_job = WhatsAppBulkJob(
        tenant_id=t_id,
        organization_id=org_id,
        tenant_code=user.tenant_code,
        title=req.get("title") or f"Bulk Broadcast {datetime.utcnow().strftime('%b %d, %H:%M')}",
        audience_type=audience_type,
        audience_payload={**audience, "sender_phone_number_id": connection.whatsapp_phone_number_id},
        message_template=message_text,
        buttons=buttons,
        media_files=media_files,
        batch_delay_seconds=batch_delay,
        scheduled_at=scheduled_at,
        status=job_status,
        stats=stats,
        recipients_summary=recipients_summary[:500],  # Cap log at 500 for compact storage
        created_by=user.id,
    )
    db.add(bulk_job)
    db.commit()
    db.refresh(bulk_job)

    # Persist each provider result. A failed or interrupted request must never
    # claim delivery, and a retry must not silently resend this same job.
    for index, recipient in enumerate(recipients_summary):
        if index and batch_delay:
            time.sleep(batch_delay)
        try:
            result = send_message(recipient["phone"], recipient["personalized_message"],
                                  template=req.get("template"), buttons=buttons, media_files=media_files, connection=connection)
            recipient.update(result)
        except HTTPException as error:
            uncertain = isinstance(error.detail, str) and any(
                phrase in error.detail.lower() for phrase in ("unconfirmed", "could not confirm")
            )
            recipient.update(status="unknown" if uncertain else "failed", error=error.detail)
        # Lock and reload so a concurrent webhook is not overwritten.
        db.refresh(bulk_job, with_for_update=True)
        current = list(bulk_job.recipients_summary)
        current[index] = dict(recipient)
        bulk_job.recipients_summary = current
        update_stats(bulk_job)
        db.commit()
    db.refresh(bulk_job)
    stats = bulk_job.stats
    msg_feedback = f"Meta accepted {stats['sent']} of {total_count} messages; {stats['failed']} failed. Delivery is confirmed separately by webhook."

    return {
        "success": stats["sent"] > 0,
        "message": msg_feedback,
        "data": model_to_dict(bulk_job),
    }


@router.get("/whatsapp/bulk")
def list_bulk_jobs(
    page: int = 1,
    limit: int = 20,
    user: User = Depends(require_organization),
    db: Session = Depends(get_db),
):
    if page < 1 or not 1 <= limit <= 200:
        raise HTTPException(400, "Use page >= 1 and limit between 1 and 200")
    t_id = tenant_id_for_user(user)
    stmt = (
        select(WhatsAppBulkJob)
        .where(
            WhatsAppBulkJob.tenant_id == t_id,
            WhatsAppBulkJob.organization_id == user.organization_id,
        )
        .order_by(WhatsAppBulkJob.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    jobs = db.scalars(stmt).all()
    return {"success": True, "data": [model_to_dict(j) for j in jobs]}


@configuration_router.get("/whatsapp/configuration")
def whatsapp_configuration(user: User = Depends(require_organization), db: Session = Depends(get_db)):
    from app.config.settings import get_settings
    settings = get_settings()
    connection = public_connection(get_connection(db, user))
    return {"success": True, "data": {
        "organization_id": user.organization_id,
        "sender_configured": connection["connected"],
        "webhook_secret_configured": bool(settings.meta_app_secret),
        "organization_authorized": connection["connected"],
        "live_features": ["text", "approved_templates", "quick_reply_buttons", "public_https_media", "delivery_webhooks"],
        "unavailable_features": ["automatic_scheduling", "local_media_upload", "automatic_replies", "group_joining", "whatsapp_number_lookup"],
    }}


@router.get("/whatsapp/bulk/{job_id}")
def get_bulk_job(
    job_id: int,
    user: User = Depends(require_organization),
    db: Session = Depends(get_db),
):
    job = ensure_tenant_access(db.get(WhatsAppBulkJob, job_id), user, "Bulk Job")
    return {"success": True, "data": model_to_dict(job)}


@router.post("/whatsapp/bulk/{job_id}/action")
def bulk_job_action(
    job_id: int,
    payload: dict[str, Any],
    user: User = Depends(require_organization),
    db: Session = Depends(get_db),
):
    job = ensure_tenant_access(db.get(WhatsAppBulkJob, job_id), user, "Bulk Job")

    action = payload.get("action")
    if action in {"resume", "run_now"}:
        raise HTTPException(400, "This job cannot be dispatched by changing its status. Create a new immediate broadcast after checking recipient delivery")
    if action in {"cancel", "pause"} and job.status in {"scheduled", "paused"}:
        job.status = "cancelled" if action == "cancel" else "paused"
    else:
        raise HTTPException(400, f"Unsupported action: {action}")

    db.commit()
    return {"success": True, "message": f"Bulk job updated to {job.status}", "data": model_to_dict(job)}
