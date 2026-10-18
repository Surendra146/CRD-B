from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
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
    return {"success": True, "data": [template_public(row) for row in rows]}


def template_public(row):
    from app.services.template_workflow import approved_definition
    data = model_to_dict(row)
    approved = approved_definition(row)
    if approved:
        data['workflow'] = {**(row.workflow or {}), 'approved': approved}
    return data


def get_template(template_id: int, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    template = db.get(WhatsAppTemplate, template_id)
    ensure_tenant_access(template, user, "Template")
    return {"success": True, "data": template_public(template)}


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
    from app.services.template_workflow import owned
    template = owned(db, user, template_id, lock=True)
    from app.services.template_workflow import approved_definition
    legacy = approved_definition(template)
    if legacy and not (template.workflow or {}).get('approved'):
        template.workflow = {**(template.workflow or {}), 'approved': legacy}
    if (template.workflow or {}).get('approved') or (template.targeting or {}).get('meta_id'):
        payload_data.pop('whatsappTemplateName', None)
        payload_data.pop('isActive', None)
    allowed = {'name', 'category', 'whatsappTemplateName', 'content', 'variables', 'isActive'}
    apply_payload(template, {k: v for k, v in payload_data.items() if k in allowed}, {"whatsappTemplateName": "whatsapp_template_name", "isActive": "is_active"})
    template.workflow = {**(template.workflow or {}), 'draft_revision': (template.workflow or {}).get('draft_revision', 1) + 1}
    db.commit()
    return {"success": True, "data": model_to_dict(template)}


def delete_template(template_id: int, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    template = db.get(WhatsAppTemplate, template_id)
    ensure_tenant_access(template, user, "Template")
    if (template.workflow or {}).get("submitted") or (template.targeting or {}).get("meta_id"):
        raise HTTPException(409, "Submitted templates are retained for queued messages; deactivate them in Meta instead")
    db.delete(template)
    db.commit()
    return {"success": True, "message": "Template deleted"}


router = APIRouter(dependencies=[Depends(require_organization)])

router.get("/")(get_templates)
router.get("/{template_id}")(get_template)
router.post("/")(create_template)
router.put("/{template_id}")(update_template)
router.delete("/{template_id}")(delete_template)





@router.post("/{template_id}/submit")
def submit_template(template_id: int, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    from app.services.template_workflow import submit
    return {"success": True, "data": model_to_dict(submit(db, user, template_id))}


@router.post("/{template_id}/refresh")
def refresh_template(template_id: int, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    from app.services.template_workflow import refresh
    return {"success": True, "data": model_to_dict(refresh(db, user, template_id))}


@router.post("/{template_id}/media")
async def upload_template_media(template_id: int, file: UploadFile = File(...), user: User = Depends(require_organization), db: Session = Depends(get_db)):
    from app.services.template_workflow import owned
    from app.services.template_media import store_asset
    row = owned(db, user, template_id, lock=True)
    data = await file.read(100 * 1024**2 + 1)
    await file.close()
    if len(data) > 100 * 1024**2:
        raise HTTPException(413, 'Upload files up to 100 MB')
    entry = store_asset(row, data, file.content_type, file.filename)
    db.commit()
    return {"success": True, "data": entry}


@router.get("/{template_id}/media/{asset_id}")
def preview_template_media(template_id: int, asset_id: str, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    from app.services.template_workflow import owned
    from app.services.template_media import asset
    entry, data = asset(owned(db, user, template_id), asset_id)
    return Response(data, media_type=entry['mime'], headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff', 'Content-Disposition': 'inline'})
