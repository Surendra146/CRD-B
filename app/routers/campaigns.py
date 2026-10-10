from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.services.crud import apply_payload, paginate
from app.database.connection import get_db
from app.utils.helpers import model_to_dict
from app.models import Campaign, Customer, User, WhatsAppTemplate, WhatsAppBulkJob
from app.schemas.campaign import CampaignCreateRequest, CampaignUpdateRequest
from app.services.security import ensure_tenant_access, require_organization, tenant_id_for_user

ACTIVE_STATUSES = {"active", "running"}


def audience_size(db: Session, user: User, audience: dict) -> int:
    if user.organization_id is None:
        return 0
    statement = select(func.count()).select_from(Customer).where(
        Customer.tenant_id == tenant_id_for_user(user),
        Customer.organization_id == user.organization_id,
    )
    filters = audience.get("filters") or {}
    if audience.get("type") == "segment":
        if filters.get("statuses"):
            statement = statement.where(Customer.lifecycle["status"].as_string().in_(filters["statuses"]))
        if filters.get("segments"):
            statement = statement.where(Customer.lifecycle["segment"].as_string().in_(filters["segments"]))
    if audience.get("type") == "custom" and audience.get("customerIds"):
        statement = statement.where(Customer.id.in_(audience["customerIds"]))
    return db.scalar(statement) or 0


def get_campaigns(page: int = 1, limit: int = 10, status: str | None = None, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    statement = select(Campaign).where(Campaign.tenant_id == tenant_id_for_user(user), Campaign.organization_id == user.organization_id)
    if status:
        statement = statement.where(Campaign.status == status)
    return paginate(db, statement.order_by(Campaign.created_at.desc()), page, limit)


def get_campaign(campaign_id: int, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    campaign = ensure_tenant_access(db.get(Campaign, campaign_id), user, "Campaign")
    return {"success": True, "data": model_to_dict(campaign)}


def create_campaign(payload: CampaignCreateRequest, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    payload_data = payload.to_payload()
    template_id = payload_data.get("template") or payload_data.get("templateId")
    if template_id is not None:
        ensure_tenant_access(db.get(WhatsAppTemplate, template_id), user, "Template")
    audience = payload_data.get("audience") or {}
    audience["estimatedReach"] = audience_size(db, user, audience)
    campaign = Campaign(
        tenant_id=tenant_id_for_user(user),
        organization_id=user.organization_id,
        tenant_code=user.tenant_code,
        name=payload_data.get("name"),
        description=payload_data.get("description"),
        type=payload_data.get("type"),
        trigger=payload_data.get("trigger") or {},
        template_id=payload_data.get("template") or payload_data.get("templateId"),
        audience=audience,
        schedule=payload_data.get("schedule") or {},
        status=payload_data.get("status", "draft"),
        stats=payload_data.get("stats") or {"totalTargeted": 0, "sent": 0, "errors": 0},
        created_by=user.id,
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return {"success": True, "data": model_to_dict(campaign)}


def update_campaign(campaign_id: int, payload: CampaignUpdateRequest, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    payload_data = payload.to_payload()
    campaign = ensure_tenant_access(db.get(Campaign, campaign_id), user, "Campaign")
    if campaign.status in [*ACTIVE_STATUSES, "completed"]:
        raise HTTPException(400, "Cannot update an active or completed campaign")
    # Validate every accepted alias before apply_payload; an explicit null alias
    # must not hide a different non-null template reference in the same request.
    for template_key in ("template", "templateId", "template_id"):
        template_id = payload_data.get(template_key)
        if template_id is not None:
            ensure_tenant_access(db.get(WhatsAppTemplate, template_id), user, "Template")
    apply_payload(campaign, payload_data, {"template": "template_id", "templateId": "template_id"})
    if campaign.audience:
        audience = campaign.audience
        audience["estimatedReach"] = audience_size(db, user, audience)
        campaign.audience = audience
    db.commit()
    return {"success": True, "data": model_to_dict(campaign)}


def delete_campaign(campaign_id: int, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    campaign = ensure_tenant_access(db.get(Campaign, campaign_id), user, "Campaign")
    if campaign.status in ACTIVE_STATUSES:
        raise HTTPException(400, "Cannot delete an active campaign")
    db.delete(campaign)
    db.commit()
    return {"success": True, "message": "Campaign deleted"}


def campaign_jobs(db, user, campaign_id):
    return db.scalars(select(WhatsAppBulkJob).where(
        WhatsAppBulkJob.tenant_id == user.tenant_id,
        WhatsAppBulkJob.organization_id == user.organization_id,
        WhatsAppBulkJob.audience_payload["campaign_id"].as_integer() == campaign_id,
    ).with_for_update()).all()


def launch_campaign(campaign_id: int, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    from app.config.settings import get_settings
    from app.schemas.whatsapp_marketing import WhatsAppBulkSendRequest
    from app.routers.communications import send_bulk_whatsapp
    campaign = ensure_tenant_access(db.scalar(select(Campaign).where(Campaign.id == campaign_id).with_for_update()), user, "Campaign")
    if campaign.status not in {"draft", "scheduled"} or campaign_jobs(db, user, campaign_id):
        raise HTTPException(409, "This campaign has already launched or cannot be launched")
    if get_settings().campaign_transport != "celery":
        raise HTTPException(409, "Campaign automation requires the Redis/Celery worker")
    template = ensure_tenant_access(db.get(WhatsAppTemplate, campaign.template_id), user, "Template")
    if not template.is_active or (template.stats or {}).get("meta_status") != "APPROVED":
        raise HTTPException(409, "Synchronize an approved WhatsApp template before launching")
    statement = select(Customer).where(Customer.tenant_id == user.tenant_id,
        Customer.organization_id == user.organization_id, Customer.phone.is_not(None))
    audience = campaign.audience or {}
    filters = audience.get("filters") or {}
    if audience.get("type") == "custom":
        ids = audience.get("customerIds") or []
        if not ids:
            raise HTTPException(400, "Select customers for this campaign")
        statement = statement.where(Customer.id.in_(ids))
    elif audience.get("type") == "segment":
        for key, field in (("statuses", "status"), ("segments", "segment")):
            if filters.get(key):
                statement = statement.where(Customer.lifecycle[field].as_string().in_(filters[key]))
    elif audience.get("type") not in {None, "all"}:
        raise HTTPException(400, "Unsupported campaign audience")
    customers = db.scalars(statement).all()
    campaign.status = "running"
    payload = WhatsAppBulkSendRequest.model_validate({
        "title": campaign.name, "audience_type": "custom_numbers",
        "audience": {"campaign_id": campaign.id, "numbers": [{"phone": c.phone, "name": c.name} for c in customers]},
        "template": {"name": template.whatsapp_template_name, "language": {"code": (template.content or {}).get("language")}},
        "scheduled_at": (campaign.schedule or {}).get("scheduledAt"),
    })
    try:
        result = send_bulk_whatsapp(payload, user, db)
    except Exception:
        db.rollback()
        raise
    return {**result, "campaignId": campaign.id}


def pause_campaign(campaign_id: int, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    return set_status(campaign_id, "paused", user, db, required=ACTIVE_STATUSES)


def resume_campaign(campaign_id: int, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    return set_status(campaign_id, "running", user, db, required={"paused"})


def complete_campaign(campaign_id: int, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    return set_status(campaign_id, "completed", user, db, required={*ACTIVE_STATUSES, "paused"}, message="Campaign completed; remaining queued recipients cancelled")


def set_status(campaign_id: int, status: str, user: User, db: Session, required: set[str], message: str | None = None):
    from app.models.saas import CampaignOutbox
    campaign = ensure_tenant_access(db.scalar(select(Campaign).where(Campaign.id == campaign_id).with_for_update()), user, "Campaign")
    if campaign.status not in required:
        raise HTTPException(400, f"Invalid campaign status '{campaign.status}'")
    for job in campaign_jobs(db, user, campaign_id):
        if status == "paused" and job.status in {"scheduled", "in_progress"}:
            job.status = "paused"
        elif status == "running" and job.status == "paused":
            job.status = "scheduled"
            job.scheduled_at = datetime.now(UTC).replace(tzinfo=None)
            outbox = db.scalar(select(CampaignOutbox).where(CampaignOutbox.bulk_job_id == job.id))
            if outbox:
                outbox.status = "pending"
                outbox.last_attempt_at = None
        elif status == "completed" and job.status in {"scheduled", "paused", "in_progress"}:
            job.status = "cancelled"
    campaign.status = status
    db.commit()
    return {"success": True, "message": message or f"Campaign {status}", "data": model_to_dict(campaign)}


router = APIRouter(dependencies=[Depends(require_organization)])

router.get("/")(get_campaigns)
router.get("/{campaign_id}")(get_campaign)
router.post("/")(create_campaign)
router.put("/{campaign_id}")(update_campaign)
router.delete("/{campaign_id}")(delete_campaign)
router.post("/{campaign_id}/launch")(launch_campaign)
router.post("/{campaign_id}/pause")(pause_campaign)
router.post("/{campaign_id}/resume")(resume_campaign)
router.post("/{campaign_id}/complete")(complete_campaign)


