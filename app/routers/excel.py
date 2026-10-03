from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.utils.helpers import model_to_dict
from app.models import DataUpload, User
from app.services.security import ensure_tenant_access, require_organization, tenant_id_for_user
from app.routers.uploads import extract_upload_metadata, get_staged_rows, stage_upload_rows





def dashboard_upload_response(upload: DataUpload, db: Session, columns: list[str] | None = None) -> dict:
    data = model_to_dict(upload)
    file_data = data.get("file") or {}
    rows = [row.raw_data for row in get_staged_rows(db, upload)]
    preview_columns = columns
    if preview_columns is None:
        valid_preview = data.get("validPreview") or data.get("valid_preview") or []
        preview_columns = valid_preview[0].get("columns") if valid_preview else []

    data["uploadId"] = data["id"]
    data["sourceName"] = file_data.get("sourceName")
    data["dashboardId"] = file_data.get("dashboardId")
    data["columns"] = preview_columns or []
    data["totalRows"] = (data.get("stats") or {}).get("totalRows") or len(rows)
    data["rawData"] = rows
    data["processedData"] = []
    return data



async def upload_excel(
    dashboardId: int | None = Form(None),
    sourceName: str | None = Form(None),
    file: UploadFile = File(...),
    user: User = Depends(require_organization),
    db: Session = Depends(get_db),
):

    content = await file.read()
    columns, total_rows, rows = extract_upload_metadata(file.filename, content)
    upload = DataUpload(
        tenant_id=tenant_id_for_user(user),
        organization_id=user.organization_id,
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
        status="uploaded",
        stats={
            "totalRows": total_rows,
            "processedRows": total_rows,
            "successRows": total_rows,
            "errorRows": 0,
            "warningRows": 0,
        },
        valid_preview=[{"columns": columns, "rows": rows[:100]}],
        error_preview=[],
        errors=[],
    )
    db.add(upload)
    db.flush()
    stage_upload_rows(db, upload, rows)
    db.commit()
    db.refresh(upload)
    return {"success": True, "data": dashboard_upload_response(upload, db, columns)}


def map_columns(payload: dict = Body(...), user: User = Depends(require_organization), db: Session = Depends(get_db)):
    raw_upload_id = payload.get("excelDataId") or payload.get("uploadId") or payload.get("id")
    if raw_upload_id is None:
        raise HTTPException(400, "excelDataId is required")
    try:
        upload_id = int(raw_upload_id)
    except (TypeError, ValueError):
        raise HTTPException(400, "excelDataId is required")

    upload = db.get(DataUpload, upload_id)
    if not upload or upload.type != "dashboard_excel":
        raise HTTPException(404, "Upload not found")
    ensure_tenant_access(upload, user, "Upload")

    column_mapping = payload.get("columnMapping") or payload.get("mappings") or {}
    upload.column_mapping = column_mapping
    upload.status = "mapped"

    db.commit()
    db.refresh(upload)
    return {"success": True, "data": dashboard_upload_response(upload, db)}


def get_upload_job_status(job_id: int, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    upload = db.get(DataUpload, job_id)
    if not upload:
        raise HTTPException(404, "Upload job not found")
    ensure_tenant_access(upload, user, "Upload job")
    return {"success": True, "data": model_to_dict(upload)}


def process_upload(upload_id: int, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    upload = db.get(DataUpload, upload_id)
    if not upload:
        raise HTTPException(404, "Upload job not found")
    ensure_tenant_access(upload, user, "Upload job")
    upload.status = "processed"
    db.commit()
    db.refresh(upload)
    return {"success": True, "data": model_to_dict(upload)}


def get_upload_status(upload_id: int, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    return get_upload_job_status(upload_id, user, db)


def get_upload_history(user: User = Depends(require_organization), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(DataUpload)
        .where(DataUpload.tenant_id == tenant_id_for_user(user), DataUpload.organization_id == user.organization_id)
        .order_by(DataUpload.created_at.desc())
    ).all()
    return {"success": True, "data": [model_to_dict(row) for row in rows]}


def get_excel_data(dashboard_id: int, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    # Dashboard model not available; filter uploads by dashboardId stored in file JSON

    uploads = db.scalars(
        select(DataUpload)
        .where(
            DataUpload.tenant_id == tenant_id_for_user(user),
            DataUpload.organization_id == user.organization_id,
            DataUpload.type == "dashboard_excel",
        )
        .order_by(DataUpload.created_at.desc())
    ).all()
    dashboard_uploads = [
        upload
        for upload in uploads
        if str((upload.file or {}).get("dashboardId")) == str(dashboard_id)
    ]
    return {
        "success": True,
        "data": [dashboard_upload_response(upload, db) for upload in dashboard_uploads],
        "dashboardId": dashboard_id,
    }


router = APIRouter(dependencies=[Depends(require_organization)])

router.post("/upload")(upload_excel)
router.post("/map-columns")(map_columns)
router.get("/upload-jobs/{job_id}/status")(get_upload_job_status)
router.get("/history")(get_upload_history)
router.post("/{upload_id}/process")(process_upload)
router.get("/{upload_id}/status")(get_upload_status)
router.get("/{dashboard_id}")(get_excel_data)




