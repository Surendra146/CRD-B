from datetime import datetime, timezone
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
from app.services.whatsapp_scheduler import parse_schedule
from app.services.meta_whatsapp import build_message, require_configuration, send_message, update_stats
from app.services.whatsapp_connections import resolve_marketing_credentials
from app.utils.helpers import model_to_dict
from app.config.settings import get_settings
from app.services.consent import assert_send_allowed, record_message
from app.services.billing import require_paid_subscription
from app.services.template_workflow import prepare_send, hydrate_media


def communication_payload(payload: CommunicationRequest) -> dict:
    return payload.to_payload()


def send_whatsapp(payload: CommunicationRequest, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    payload_data = communication_payload(payload)
    if get_settings().enforce_subscription:
        require_paid_subscription(db, user)
    credentials = resolve_marketing_credentials(db, user)
    recipient = payload_data.get('recipient') or {}
    if not isinstance(recipient, dict):
        raise HTTPException(422, 'Recipient context must be an object')
    recipient = {**recipient, 'phone': payload_data.get('phone') or payload_data.get('to')}
    customer = db.scalar(select(Customer).where(Customer.tenant_id == user.tenant_id,
        Customer.organization_id == user.organization_id,
        Customer.phone == (payload_data.get('phone') or payload_data.get('to')))) if payload_data.get('template') else None
    if customer:
        recipient = {**recipient, 'name': customer.name, 'phone': customer.phone, 'email': customer.email,
                     'lifecycle': customer.lifecycle or {}, 'demographics': customer.demographics or {}}
    approved_payload, snapshot = prepare_send(db, user, payload_data, credentials, recipient)
    if approved_payload:
        payload_data['template'] = approved_payload
        payload_data['buttons'], payload_data['media_files'] = [], []
    if get_settings().enforce_whatsapp_consent:
        assert_send_allowed(db, user.tenant_id, user.organization_id, payload_data.get("phone") or payload_data.get("to"), payload_data.get("template"), credentials.whatsapp_waba_id)
    if approved_payload:
        payload_data['template'] = hydrate_media(db, user, approved_payload, snapshot, credentials)
    result = send_message(
        payload_data.get("phone") or payload_data.get("to"), payload_data.get("message") or "",
        template=payload_data.get("template"), buttons=payload_data.get("buttons"),
        media_files=payload_data.get("media_files"),
        connection=credentials,
    )
    if hasattr(db, "execute"):
        record_message(db, user.tenant_id, user.organization_id, credentials.whatsapp_phone_number_id, payload_data.get("phone") or payload_data.get("to"), result)
        db.commit()
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
        raise HTTPException(400, "Broadcast delay must be between 0 and 5 seconds")
    scheduled_at_raw = req.get("scheduled_at") or req.get("scheduledAt")

    scheduled_at = parse_schedule(scheduled_at_raw)
    if get_settings().enforce_subscription:
        require_paid_subscription(db, user)
    connection = resolve_marketing_credentials(db, user)
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
                    'email': item.get('email'),
                    'city': item.get('city'),
                    'lifecycle': item.get('lifecycle') or {},
                    'demographics': item.get('demographics') or {},
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
    if len(recipients_data) > get_settings().max_broadcast_recipients:
        raise HTTPException(400, f"Send up to {get_settings().max_broadcast_recipients} recipients per broadcast")

    # Generate personalized messages for each recipient
    recipients_summary = []
    template_snapshot = None
    for rec in recipients_data:
        msg = personalize_message(message_text, rec)
        approved_payload, template_snapshot = prepare_send(db, user, req, connection, rec)
        if approved_payload and template_snapshot:
            from app.services.template_definitions import rendered_body
            msg = rendered_body(template_snapshot['definition'], approved_payload)
        build_message(rec.get("phone"), msg, template=approved_payload, buttons=buttons, media_files=media_files)
        recipients_summary.append({
            "name": rec.get("name"),
            "phone": rec.get("phone"),
            "personalized_message": msg,
            "status": "queued",
            "delivered_at": None,
            "approved_template": approved_payload,
        })

    asynchronous = get_settings().campaign_transport == "celery"
    if asynchronous and not scheduled_at:
        scheduled_at = datetime.now(timezone.utc).replace(tzinfo=None)
    job_status = "scheduled" if scheduled_at else "in_progress"
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
        title=req.get("title") or f"Bulk Broadcast {datetime.now(timezone.utc).strftime('%b %d, %H:%M')}",
        audience_type=audience_type,
        audience_payload={**audience, "sender_phone_number_id": connection.whatsapp_phone_number_id,
                          "meta_template": recipients_summary[0].get('approved_template'), 'template_snapshot': template_snapshot},
        message_template=message_text,
        buttons=buttons,
        media_files=media_files,
        batch_delay_seconds=batch_delay,
        scheduled_at=scheduled_at,
        status=job_status,
        stats=stats,
        recipients_summary=recipients_summary,
        created_by=user.id,
    )
    db.add(bulk_job)
    if asynchronous:
        from app.models.saas import CampaignOutbox
        db.flush()
        db.add(CampaignOutbox(tenant_id=t_id, organization_id=org_id, bulk_job_id=bulk_job.id))
    db.commit()
    db.refresh(bulk_job)

    if scheduled_at:
        return {"success": True, "message": "Campaign scheduled; messages have not been sent yet", "data": model_to_dict(bulk_job)}
    return dispatch_bulk_job(db, bulk_job, connection)


def dispatch_bulk_job(db, bulk_job, connection):
    batch_delay = bulk_job.batch_delay_seconds
    # Persist each provider result. A failed or interrupted request must never
    # claim delivery, and a retry must not silently resend this same job.
    for index, recipient in enumerate(list(bulk_job.recipients_summary)):
        if recipient.get("status") != "queued":
            continue
        if index and batch_delay:
            time.sleep(batch_delay)
        if bulk_job.status in {"paused", "cancelled"}:
            break
        db.refresh(bulk_job, with_for_update=True)
        current = list(bulk_job.recipients_summary)
        if bulk_job.status in {"paused", "cancelled"}:
            break
        if current[index].get("status") != "queued":
            continue
        # Persist uncertainty before contacting Meta; never automatically retry a
        # recipient whose acceptance was interrupted by a process restart.
        db.refresh(bulk_job, with_for_update=True)
        current = list(bulk_job.recipients_summary)
        current[index] = {**recipient, "status": "unknown"}
        bulk_job.recipients_summary = current
        db.commit()
        try:
            template_payload = recipient.get('approved_template') or bulk_job.audience_payload.get('meta_template')
            snapshot = bulk_job.audience_payload.get('template_snapshot')
            if template_payload:
                from types import SimpleNamespace
                from app.services.template_workflow import verify_queued
                scoped_user = SimpleNamespace(tenant_id=bulk_job.tenant_id, organization_id=bulk_job.organization_id)
                if snapshot:
                    verify_queued(db, scoped_user, snapshot, connection)
                else:
                    # Validate jobs queued by an older application version too.
                    template_payload, snapshot = prepare_send(db, scoped_user, {'template': template_payload}, connection, recipient)
                template_payload = hydrate_media(db, scoped_user, template_payload, snapshot, connection)
            assert_send_allowed(db, bulk_job.tenant_id, bulk_job.organization_id, recipient["phone"], template_payload, getattr(connection, "whatsapp_waba_id", None))
            if get_settings().enforce_subscription:
                from app.models import User
                creator = db.get(User, bulk_job.created_by)
                require_paid_subscription(db, creator)
            result = send_message(recipient["phone"], recipient["personalized_message"],
                                  template=template_payload, buttons=[] if template_payload else bulk_job.buttons, media_files=[] if template_payload else bulk_job.media_files, connection=connection)
            recipient.update(result)
            if hasattr(db, "execute"):
                record_message(db, bulk_job.tenant_id, bulk_job.organization_id, connection.whatsapp_phone_number_id, recipient["phone"], result, bulk_job.id)
        except HTTPException as error:
            uncertain = isinstance(error.detail, str) and any(
                phrase in error.detail.lower() for phrase in ("unconfirmed", "could not confirm")
            )
            recipient.update(status="unknown" if uncertain else "failed", error=error.detail)
        # Lock and reload so a concurrent webhook is not overwritten.
        db.refresh(bulk_job, with_for_update=True)
        current = list(bulk_job.recipients_summary)
        # Preserve a delivery webhook that arrived while Meta was responding.
        if current[index].get("status") not in {"sent", "delivered", "read", "failed"}:
            current[index] = dict(recipient)
        bulk_job.recipients_summary = current
        update_stats(bulk_job)
        db.commit()
    db.refresh(bulk_job)
    stats = bulk_job.stats
    msg_feedback = f"Meta accepted {stats['sent']} of {stats['total']} messages; {stats['failed']} failed. Delivery is confirmed separately by webhook."

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
    sender = None
    sender_error = None
    try:
        credentials = resolve_marketing_credentials(db, user)
        sender = {"phone_number_id": credentials.whatsapp_phone_number_id, "waba_id": credentials.whatsapp_waba_id}
    except HTTPException as error:
        sender_error = error.detail
    connection = {"connected": sender is not None}
    return {"success": True, "data": {
        "organization_id": user.organization_id,
        "max_broadcast_recipients": settings.max_broadcast_recipients,
        "sender": sender,
        "sender_error": sender_error,
        "sender_configured": connection["connected"],
        "webhook_secret_configured": bool(settings.meta_app_secret),
        "organization_authorized": connection["connected"],
        "live_features": ["text", "approved_templates", "quick_reply_buttons", "public_https_media", "delivery_webhooks", "automatic_scheduling"],
        "unavailable_features": ["local_media_upload", "automatic_replies", "group_joining", "whatsapp_number_lookup"],
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
    job = ensure_tenant_access(db.scalar(select(WhatsAppBulkJob).where(WhatsAppBulkJob.id == job_id).with_for_update()), user, "Bulk Job")

    action = payload.get("action")
    if action in {"resume", "run_now"} and job.status in {"scheduled", "paused", "in_progress"}:
        job.status = "scheduled"
        if action == "run_now":
            job.scheduled_at = datetime.now(timezone.utc).replace(tzinfo=None)
    elif action in {"cancel", "pause"} and job.status in {"scheduled", "paused", "in_progress"}:
        job.status = "cancelled" if action == "cancel" else "paused"
    else:
        raise HTTPException(400, f"Unsupported action: {action}")

    db.commit()
    return {"success": True, "message": f"Bulk job updated to {job.status}", "data": model_to_dict(job)}
