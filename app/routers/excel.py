from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.utils.helpers import model_to_dict
from app.models import DataUpload, User
from app.schemas.excel import ColumnMappingRequest
from app.services.security import get_current_user



async def upload_excel(
    dashboardId: int | None = Form(None),
    sourceName: str | None = Form(None),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    content = await file.read()
    upload = DataUpload(
        organization_id=user.organization_id or 0,
        tenant_code=user.tenant_code,
        uploaded_by=user.id,
        file={
            "originalName": file.filename,
            "storedName": file.filename,
            "mimeType": file.content_type,
            "size": len(content),
            "dashboardId": dashboardId,
            "sourceName": sourceName,
        },
        type="dashboard_excel",
        status="pending",
    )
    db.add(upload)
    db.commit()
    db.refresh(upload)
    return {"success": True, "data": model_to_dict(upload)}


def map_columns(payload: ColumnMappingRequest):
    payload = payload.to_payload()
    return {"success": True, "data": payload.get("mappings") or payload.get("columnMapping") or []}


def get_upload_job_status(job_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    upload = db.get(DataUpload, job_id)
    if not upload:
        raise HTTPException(404, "Upload job not found")
    return {"success": True, "data": model_to_dict(upload)}


def process_upload(upload_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    upload = db.get(DataUpload, upload_id)
    if not upload or upload.uploaded_by != user.id:
        raise HTTPException(404, "Upload job not found")
    upload.status = "processed"
    db.commit()
    db.refresh(upload)
    return {"success": True, "data": model_to_dict(upload)}


def get_upload_status(upload_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_upload_job_status(upload_id, user, db)


def get_upload_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(DataUpload).where(DataUpload.uploaded_by == user.id).order_by(DataUpload.created_at.desc())).all()
    return {"success": True, "data": [model_to_dict(row) for row in rows]}


def get_excel_data(dashboard_id: int):
    return {"success": True, "data": [], "dashboardId": dashboard_id}


router = APIRouter(dependencies=[Depends(get_current_user)])

router.post("/upload")(upload_excel)
router.post("/map-columns")(map_columns)
router.get("/upload-jobs/{job_id}/status")(get_upload_job_status)
router.get("/history")(get_upload_history)
router.post("/{upload_id}/process")(process_upload)
router.get("/{upload_id}/status")(get_upload_status)
router.get("/{dashboard_id}")(get_excel_data)




