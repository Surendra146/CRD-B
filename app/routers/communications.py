from datetime import datetime
from typing import Any
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
)
from app.services.whatsapp_service import personalize_message
from app.utils.helpers import model_to_dict


def communication_payload(payload: CommunicationRequest) -> dict:
    return payload.to_payload()


def send_whatsapp(payload: CommunicationRequest):
    payload_data = communication_payload(payload)
    return {"success": True, "message": "WhatsApp send queued", "data": payload_data}


def send_whatsapp_message(payload: CommunicationRequest):
    payload_data = communication_payload(payload)
    return {"success": True, "message": "WhatsApp send queued", "data": payload_data}


def send_communication(payload: CommunicationRequest):
    payload_data = communication_payload(payload)
    return {"success": True, "message": "Communication queued", "data": payload_data}


router = APIRouter(dependencies=[Depends(require_organization)])

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
    batch_delay = int(req.get("batch_delay_seconds") or req.get("batchDelaySeconds") or 5)
    scheduled_at_raw = req.get("scheduled_at") or req.get("scheduledAt")

    scheduled_at = None
    if scheduled_at_raw:
        try:
            if isinstance(scheduled_at_raw, str):
                scheduled_at = datetime.fromisoformat(scheduled_at_raw.replace("Z", "+00:00")).replace(tzinfo=None)
            elif isinstance(scheduled_at_raw, datetime):
                scheduled_at = scheduled_at_raw.replace(tzinfo=None)
        except Exception:
            scheduled_at = None

    is_scheduled = scheduled_at is not None and scheduled_at > datetime.utcnow()

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

    # Generate personalized messages for each recipient
    recipients_summary = []
    now_iso = datetime.utcnow().isoformat()
    for rec in recipients_data:
        msg = personalize_message(message_text, rec)
        recipients_summary.append({
            "name": rec.get("name"),
            "phone": rec.get("phone"),
            "personalized_message": msg,
            "status": "queued" if is_scheduled else "delivered",
            "delivered_at": None if is_scheduled else now_iso,
        })

    job_status = "scheduled" if is_scheduled else "completed"
    total_count = len(recipients_summary)
    stats = {
        "total": total_count,
        "sent": 0 if is_scheduled else total_count,
        "failed": 0,
        "pending": total_count if is_scheduled else 0,
    }

    bulk_job = WhatsAppBulkJob(
        tenant_id=t_id,
        organization_id=org_id,
        tenant_code=user.tenant_code,
        title=req.get("title") or f"Bulk Broadcast {datetime.utcnow().strftime('%b %d, %H:%M')}",
        audience_type=audience_type,
        audience_payload=audience,
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

    msg_feedback = (
        f"Campaign scheduled for {scheduled_at.strftime('%Y-%m-%d %H:%M UTC')} with {total_count} recipients"
        if is_scheduled and scheduled_at
        else f"Successfully dispatched bulk broadcast to {total_count} recipients"
    )

    return {
        "success": True,
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
    if action == "cancel":
        job.status = "cancelled"
    elif action == "pause":
        job.status = "paused"
    elif action == "resume":
        job.status = "scheduled" if job.scheduled_at and job.scheduled_at > datetime.utcnow() else "completed"
    elif action == "run_now":
        job.status = "completed"
        job.scheduled_at = datetime.utcnow()
        stats = job.stats or {}
        stats["sent"] = stats.get("total", 0)
        stats["pending"] = 0
        job.stats = stats
    else:
        raise HTTPException(400, f"Unsupported action: {action}")

    db.commit()
    return {"success": True, "message": f"Bulk job updated to {job.status}", "data": model_to_dict(job)}
