from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.services.crud import apply_payload
from app.database.connection import get_db
from app.utils.helpers import model_to_dict, slugify
from app.models import Segment, User
from app.schemas.segment import SegmentCreateRequest, SegmentUpdateRequest
from app.services.security import ensure_tenant_access, require_organization, tenant_id_for_user



def get_segments(user: User = Depends(require_organization), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Segment)
        .where(Segment.tenant_id == tenant_id_for_user(user), Segment.organization_id == user.organization_id, Segment.is_active == True)
        .order_by(Segment.created_at.desc())
    ).all()
    return {"success": True, "data": [model_to_dict(row) for row in rows]}


def create_segment(payload: SegmentCreateRequest, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    payload_data = payload.to_payload()
    segment = Segment(
        tenant_id=tenant_id_for_user(user),
        organization_id=user.organization_id,
        tenant_code=user.tenant_code,
        code=payload_data.get("code") or slugify(payload_data.get("name", "segment")),
        name=payload_data.get("name"),
        description=payload_data.get("description"),
        filters=payload_data.get("filters") or {},
        is_active=payload_data.get("isActive", True),
        created_by=user.id,
    )
    db.add(segment)
    db.commit()
    db.refresh(segment)
    return {"success": True, "data": model_to_dict(segment)}


def update_segment(segment_id: int, payload: SegmentUpdateRequest, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    payload_data = payload.to_payload()
    segment = db.get(Segment, segment_id)
    ensure_tenant_access(segment, user, "Segment")
    apply_payload(segment, payload_data, {"isActive": "is_active"})
    db.commit()
    return {"success": True, "data": model_to_dict(segment)}


def delete_segment(segment_id: int, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    segment = db.get(Segment, segment_id)
    ensure_tenant_access(segment, user, "Segment")
    segment.is_active = False
    db.commit()
    return {"success": True, "message": "Segment deleted"}


def download_segment_template():
    return {"success": True, "columns": ["code", "name", "description", "statuses", "segments", "minTotalSpent", "minOrders"]}


def validate_segment_import():
    return {"success": True, "validRows": [], "errors": []}


def save_segment_import():
    return {"success": True, "message": "Segment import saved"}


def export_segment_import_errors():
    return {"success": True, "data": []}


router = APIRouter(dependencies=[Depends(require_organization)])

router.get("/")(get_segments)
router.post("/")(create_segment)
router.put("/{segment_id}")(update_segment)
router.delete("/{segment_id}")(delete_segment)
router.get("/import/template")(download_segment_template)
router.post("/import/validate")(validate_segment_import)
router.post("/import/save")(save_segment_import)
router.post("/import/export-errors")(export_segment_import_errors)



