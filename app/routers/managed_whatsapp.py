from datetime import UTC, datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models import Organization, User, WhatsAppConnection, WhatsAppTemplate
from app.services.audit import audit
from app.services.billing import number_limit
from app.services.security import require_owner, require_organization, require_module
from app.services.whatsapp_connections import decrypt_token, get_connection, graph, public_connection

router = APIRouter()


@router.get("/numbers")
def numbers(user: User = Depends(require_organization), db: Session = Depends(get_db)):
    rows = db.scalars(select(WhatsAppConnection).where(WhatsAppConnection.tenant_id == user.tenant_id,
        WhatsAppConnection.organization_id == user.organization_id).order_by(WhatsAppConnection.id)).all()
    return {"success": True, "data": [public_connection(row) for row in rows]}


@router.post("/numbers/{phone_number_id}/default")
def default_sender(phone_number_id: str, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    db.scalar(select(Organization).where(Organization.id == user.organization_id).with_for_update())
    connection = get_connection(db, user, phone_number_id)
    if not connection:
        raise HTTPException(404, "Business WhatsApp number not found")
    db.execute(update(WhatsAppConnection).where(WhatsAppConnection.tenant_id == user.tenant_id,
        WhatsAppConnection.organization_id == user.organization_id).values(is_default=False))
    db.flush()
    connection.is_default = True
    audit(db, user, "whatsapp.default_sender.updated", phone_number_id)
    db.commit()
    return {"success": True}


@router.delete("/numbers/{phone_number_id}")
def disconnect_number(phone_number_id: str, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    db.scalar(select(Organization).where(Organization.id == user.organization_id).with_for_update())
    connection = get_connection(db, user, phone_number_id)
    if not connection:
        raise HTTPException(404, "Business WhatsApp number not found")
    was_default = connection.is_default
    db.delete(connection)
    db.flush()
    if was_default:
        other = get_connection(db, user)
        if other:
            other.is_default = True
    audit(db, user, "whatsapp.sender.disconnected", phone_number_id)
    db.commit()
    return {"success": True}


@router.post("/templates/sync")
def sync_templates(user: User = Depends(require_module("templates", "whatsapp")), db: Session = Depends(get_db)):
    connections = db.scalars(select(WhatsAppConnection).where(WhatsAppConnection.tenant_id == user.tenant_id,
        WhatsAppConnection.organization_id == user.organization_id)).all()
    if not connections:
        raise HTTPException(409, "Connect your business WhatsApp number first")
    count = 0
    visited = set()
    for connection in connections:
        if connection.waba_id in visited:
            continue
        visited.add(connection.waba_id)
        token = decrypt_token(connection.encrypted_access_token, connection.tenant_id, connection.organization_id)
        after = None
        provider_templates = []
        for _ in range(100):
            params = {"fields": "id,name,status,category,language,components", "limit": 100}
            if after:
                params["after"] = after
            page = graph(connection.waba_id + "/message_templates", token, params=params)
            provider_templates.extend(page.get("data", []))
            paging = page.get("paging") or {}
            if not paging.get("next"):
                break
            next_after = (paging.get("cursors") or {}).get("after")
            if not next_after or next_after == after:
                raise HTTPException(502, "Meta template pagination could not be completed")
            after = next_after
        else:
            raise HTTPException(502, "Meta template synchronization exceeded the page limit")
        # Mark absent templates inactive after a complete provider snapshot.
        current = db.scalars(select(WhatsAppTemplate).where(WhatsAppTemplate.tenant_id == user.tenant_id,
            WhatsAppTemplate.organization_id == user.organization_id,
            WhatsAppTemplate.targeting["waba_id"].as_string() == connection.waba_id)).all()
        for row in current:
            row.is_active = False
        for item in provider_templates:
            if not isinstance(item, dict) or not all(item.get(key) for key in ("id", "name", "language", "category", "status")):
                raise HTTPException(502, "Meta returned an incomplete template")
            row = next((row for row in current if (row.targeting or {}).get("meta_id") == item["id"]), None)
            if not row:
                row = WhatsAppTemplate(tenant_id=user.tenant_id, organization_id=user.organization_id,
                    name=item["name"], category=item["category"], whatsapp_template_name=item["name"])
                db.add(row)
            row.content = {"components": item.get("components") or [], "language": item["language"]}
            row.targeting = {"waba_id": connection.waba_id, "meta_id": item["id"]}
            row.stats = {"meta_status": item["status"], "synced_at": datetime.now(UTC).isoformat()}
            row.category = item["category"]
            row.is_active = item["status"] == "APPROVED"
            count += 1
    audit(db, user, "whatsapp.templates.synchronized", details={"count": count})
    db.commit()
    return {"success": True, "data": {"templates": count}}
