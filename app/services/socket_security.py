"""Apply the HTTP identity, module and tenant checks to upload socket subscriptions."""
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from app.database.connection import ControlSessionLocal, SessionLocal
from app.models import DataUpload
from app.services.security import ensure_tenant_access, get_current_user, require_module


def authorize_upload_socket(token, upload_id=None):
    if not isinstance(token, str) or not token:
        raise HTTPException(401, "Authentication required")
    request = Request({"type": "http", "method": "GET", "path": "/socket.io", "headers": []})
    with ControlSessionLocal() as control, SessionLocal() as db:
        user = get_current_user(request, HTTPAuthorizationCredentials(scheme="Bearer", credentials=token), control, db)
        require_module("uploads", "import", "reports")(request, user)
        if upload_id is not None:
            try:
                if isinstance(upload_id, bool):
                    raise ValueError
                upload_id = int(upload_id)
                if upload_id <= 0:
                    raise ValueError
            except (ValueError, TypeError):
                raise HTTPException(400, "A valid uploadId is required") from None
            ensure_tenant_access(db.get(DataUpload, upload_id), user, "Upload")
        return upload_id
