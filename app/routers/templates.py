from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.services.crud import apply_payload
from app.database.connection import get_db
from app.utils.helpers import model_to_dict
from app.models import User, WhatsAppTemplate
from app.schemas.template import TemplateCreateRequest, TemplateUpdateRequest
from app.services.security import ensure_tenant_access, require_organization, tenant_id_for_user



def get_templates(user: User = Depends(require_organization), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(WhatsAppTemplate)
        .where(WhatsAppTemplate.tenant_id == tenant_id_for_user(user), WhatsAppTemplate.organization_id == user.organization_id)
        .order_by(WhatsAppTemplate.created_at.desc())
    ).all()
    return {"success": True, "data": [model_to_dict(row) for row in rows]}


def get_template(template_id: int, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    template = db.get(WhatsAppTemplate, template_id)
    ensure_tenant_access(template, user, "Template")
    return {"success": True, "data": model_to_dict(template)}


def create_template(payload: TemplateCreateRequest, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    payload_data = payload.to_payload()
    template = WhatsAppTemplate(
        tenant_id=tenant_id_for_user(user),
        organization_id=user.organization_id,
        tenant_code=user.tenant_code,
        name=payload_data.get("name"),
        category=payload_data.get("category"),
        whatsapp_template_name=payload_data.get("whatsappTemplateName"),
        content=payload_data.get("content") or {},
        variables=payload_data.get("variables") or [],
        targeting=payload_data.get("targeting") or {},
        stats=payload_data.get("stats") or {},
        is_active=payload_data.get("isActive", True),
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return {"success": True, "data": model_to_dict(template)}


def update_template(template_id: int, payload: TemplateUpdateRequest, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    payload_data = payload.to_payload()
    template = db.get(WhatsAppTemplate, template_id)
    ensure_tenant_access(template, user, "Template")
    apply_payload(template, payload_data, {"whatsappTemplateName": "whatsapp_template_name", "isActive": "is_active"})
    db.commit()
    return {"success": True, "data": model_to_dict(template)}


def delete_template(template_id: int, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    template = db.get(WhatsAppTemplate, template_id)
    ensure_tenant_access(template, user, "Template")
    db.delete(template)
    db.commit()
    return {"success": True, "message": "Template deleted"}


router = APIRouter(dependencies=[Depends(require_organization)])

router.get("/")(get_templates)
router.get("/{template_id}")(get_template)
router.post("/")(create_template)
router.put("/{template_id}")(update_template)
router.delete("/{template_id}")(delete_template)



