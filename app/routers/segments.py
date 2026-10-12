from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.services.crud import apply_payload
from app.database.connection import get_db
from app.utils.helpers import model_to_dict, slugify
from app.models import Customer, Segment, User
from app.services.api_exports import excel_response, error_excel_response
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
    return excel_response(["customerCode", "segmentCode"], [], "customer-segment-template.xlsx")


def validate_segment_rows(rows, user, db):
    customers = db.scalars(select(Customer).where(
        Customer.tenant_id == tenant_id_for_user(user), Customer.organization_id == user.organization_id,
        Customer.external_id.in_([str(row.get("customerCode") or "").strip() for row in rows]),
    )).all()
    segments = db.scalars(select(Segment).where(
        Segment.tenant_id == tenant_id_for_user(user), Segment.organization_id == user.organization_id,
        Segment.is_active.is_(True),
        Segment.code.in_([str(row.get("segmentCode") or "").strip() for row in rows]),
    )).all()
    by_customer = {}
    for customer in customers:
        by_customer.setdefault(customer.external_id, []).append(customer)
    by_segment = {segment.code: segment for segment in segments}
    valid, errors, seen = [], [], set()
    for index, row in enumerate(rows, start=2):
        data = {key: str(row.get(key) or "").strip() for key in ("customerCode", "segmentCode")}
        code, segment = data["customerCode"], data["segmentCode"]
        message = None
        if not code or not segment:
            message = "customerCode and segmentCode are required"
        elif code not in by_customer:
            message = "Customer code not found in this organization"
        elif len(by_customer[code]) != 1:
            message = "Customer code is ambiguous in this organization"
        elif segment not in by_segment:
            message = "Active segment code not found in this organization"
        elif code in seen:
            message = "Duplicate customer code in this file"
        seen.add(code)
        if message:
            errors.append({"row": index, "message": message, "data": data})
        else:
            valid.append(data)
    return {"totalRows": len(rows), "validCount": len(valid), "errorCount": len(errors),
            "validRows": valid, "errors": errors}, by_customer


async def validate_segment_import(file: UploadFile = File(...), user: User = Depends(require_organization), db: Session = Depends(get_db)):
    from app.routers.uploads import extract_upload_metadata
    try:
        columns, total, rows = extract_upload_metadata(file.filename, await file.read())
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "Unable to read this spreadsheet") from None
    if not {"customerCode", "segmentCode"}.issubset(columns):
        raise HTTPException(400, "The file must contain customerCode and segmentCode columns")
    if total > 5000:
        raise HTTPException(400, "Import up to 5000 segment mappings at a time")
    result, _ = validate_segment_rows(rows, user, db)
    return {"success": True, "data": result}


class SegmentMappingRow(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    customerCode: str = Field(min_length=1, max_length=255)
    segmentCode: str = Field(min_length=1, max_length=255)


class SegmentImportPayload(BaseModel):
    validRows: list[SegmentMappingRow] = Field(min_length=1, max_length=5000)


class SegmentErrorsPayload(BaseModel):
    errors: list[dict] = Field(max_length=5000)


def save_segment_import(payload: SegmentImportPayload, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    # Revalidate on save: browser-supplied validated rows are not an authorization boundary.
    result, customers = validate_segment_rows([row.model_dump() for row in payload.validRows], user, db)
    if result["errors"]:
        raise HTTPException(400, "Segment mappings changed or are invalid; validate the file again")
    for row in result["validRows"]:
        customer = customers[row["customerCode"]][0]
        customer.lifecycle = {**(customer.lifecycle or {}), "segment": row["segmentCode"]}
    db.commit()
    return {"success": True, "data": {"savedRows": len(result["validRows"]), "failedRows": 0, "totalRows": result["totalRows"]}}


def export_segment_import_errors(payload: SegmentErrorsPayload):
    return error_excel_response(payload.errors, "customer-segment-import-errors.xlsx")


router = APIRouter(dependencies=[Depends(require_organization)])

router.get("/")(get_segments)
router.post("/")(create_segment)
router.put("/{segment_id}")(update_segment)
router.delete("/{segment_id}")(delete_segment)
router.get("/import/template")(download_segment_template)
router.post("/import/validate")(validate_segment_import)
router.post("/import/save")(save_segment_import)
router.post("/import/export-errors")(export_segment_import_errors)



