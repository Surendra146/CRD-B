from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.services.crud import apply_payload
from app.database.connection import get_db
from app.utils.helpers import model_to_dict
from app.models import User, WhatsAppTemplate
from app.schemas.template import TemplateCreateRequest, TemplateUpdateRequest
from app.services.security import require_organization



def get_templates(user: User = Depends(require_organization), db: Session = Depends(get_db)):
    rows = db.scalars(select(WhatsAppTemplate).where(WhatsAppTemplate.organization_id == user.organization_id).order_by(WhatsAppTemplate.created_at.desc())).all()
    return {"success": True, "data": [model_to_dict(row) for row in rows]}


def get_template(template_id: int, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    template = db.get(WhatsAppTemplate, template_id)
    if not template or template.organization_id != user.organization_id:
        raise HTTPException(404, "Template not found")
    return {"success": True, "data": model_to_dict(template)}


def create_template(payload: TemplateCreateRequest, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    payload = payload.to_payload()
    template = WhatsAppTemplate(
        organization_id=user.organization_id,
        tenant_code=user.tenant_code,
        name=payload.get("name"),
        category=payload.get("category"),
        whatsapp_template_name=payload.get("whatsappTemplateName"),
        content=payload.get("content") or {},
        variables=payload.get("variables") or [],
        targeting=payload.get("targeting") or {},
        stats=payload.get("stats") or {},
        is_active=payload.get("isActive", True),
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return {"success": True, "data": model_to_dict(template)}


def update_template(template_id: int, payload: TemplateUpdateRequest, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    payload = payload.to_payload()
    template = db.get(WhatsAppTemplate, template_id)
    if not template or template.organization_id != user.organization_id:
        raise HTTPException(404, "Template not found")
    apply_payload(template, payload, {"whatsappTemplateName": "whatsapp_template_name", "isActive": "is_active"})
    db.commit()
    return {"success": True, "data": model_to_dict(template)}


def delete_template(template_id: int, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    template = db.get(WhatsAppTemplate, template_id)
    if not template or template.organization_id != user.organization_id:
        raise HTTPException(404, "Template not found")
    db.delete(template)
    db.commit()
    return {"success": True, "message": "Template deleted"}


router = APIRouter(dependencies=[Depends(require_organization)])

router.get("/")(get_templates)
router.get("/{template_id}")(get_template)
router.post("/")(create_template)
router.put("/{template_id}")(update_template)
router.delete("/{template_id}")(delete_template)




