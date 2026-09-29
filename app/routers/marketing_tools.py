from datetime import datetime
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models import (
    Customer,
    GoogleMapsLead,
    User,
    WhatsAppAutoResponder,
    WhatsAppGroupTask,
)
from app.schemas.whatsapp_marketing import (
    AutoResponderCreateRequest,
    AutoResponderTestRequest,
    AutoResponderUpdateRequest,
    GMapsImportRequest,
    GMapsSearchRequest,
    GroupTaskCreateRequest,
    NumberFilterRequest,
)
from app.services.crud import apply_payload
from app.services.gmaps_service import (
    import_gmaps_leads_to_customers,
    search_google_maps_leads,
)
from app.services.security import (
    ensure_tenant_access,
    require_organization,
    tenant_id_for_user,
)
from app.services.whatsapp_service import (
    evaluate_auto_responder,
    filter_phone_numbers,
    grab_members_from_text,
    parse_group_links,
)
from app.utils.helpers import model_to_dict

router = APIRouter(dependencies=[Depends(require_organization)])


# =====================================================================
# 1. WHATSAPP NUMBER FILTER
# =====================================================================
@router.post("/filter-numbers")
def filter_numbers_endpoint(
    payload: NumberFilterRequest,
    user: User = Depends(require_organization),
):
    req = payload.to_payload()
    numbers = req.get("numbers") or []
    default_prefix = req.get("default_country_code") or "+91"
    result = filter_phone_numbers(numbers, default_prefix)
    return {"success": True, "data": result}


# =====================================================================
# 2. GOOGLE MAPS DATA EXTRACTOR
# =====================================================================
@router.post("/gmaps-extractor/search")
def gmaps_search_endpoint(
    payload: GMapsSearchRequest,
    user: User = Depends(require_organization),
):
    req = payload.to_payload()
    query = req.get("query") or "Businesses"
    location = req.get("location") or "Hyderabad"
    limit = int(req.get("limit") or 25)

    leads = search_google_maps_leads(query, location, limit)
    return {"success": True, "data": leads, "count": len(leads)}


@router.post("/gmaps-extractor/import")
def gmaps_import_endpoint(
    payload: GMapsImportRequest,
    user: User = Depends(require_organization),
    db: Session = Depends(get_db),
):
    req = payload.to_payload()
    leads = req.get("leads") or []
    tag = req.get("tag")

    if not leads:
        raise HTTPException(400, "No leads provided to import")

    result = import_gmaps_leads_to_customers(db, user, leads, tag)
    return result


@router.get("/gmaps-extractor/history")
def gmaps_history_endpoint(
    user: User = Depends(require_organization),
    db: Session = Depends(get_db),
):
    t_id = tenant_id_for_user(user)
    leads = db.scalars(
        select(GoogleMapsLead)
        .where(
            GoogleMapsLead.tenant_id == t_id,
            GoogleMapsLead.organization_id == user.organization_id,
        )
        .order_by(GoogleMapsLead.created_at.desc())
        .limit(100)
    ).all()
    return {"success": True, "data": [model_to_dict(l) for l in leads]}


# =====================================================================
# 3. AUTO RESPONDER
# =====================================================================
@router.get("/auto-responder")
def get_auto_responder_rules(
    user: User = Depends(require_organization),
    db: Session = Depends(get_db),
):
    t_id = tenant_id_for_user(user)
    rules = db.scalars(
        select(WhatsAppAutoResponder)
        .where(
            WhatsAppAutoResponder.tenant_id == t_id,
            WhatsAppAutoResponder.organization_id == user.organization_id,
        )
        .order_by(WhatsAppAutoResponder.priority.desc(), WhatsAppAutoResponder.created_at.desc())
    ).all()
    return {"success": True, "data": [model_to_dict(r) for r in rules]}


@router.post("/auto-responder")
def create_auto_responder_rule(
    payload: AutoResponderCreateRequest,
    user: User = Depends(require_organization),
    db: Session = Depends(get_db),
):
    req = payload.to_payload()
    rule = WhatsAppAutoResponder(
        tenant_id=tenant_id_for_user(user),
        organization_id=user.organization_id,
        tenant_code=user.tenant_code,
        name=req.get("name"),
        trigger_type=req.get("trigger_type") or req.get("triggerType", "contains"),
        keywords=req.get("keywords") or [],
        response_message=req.get("response_message") or req.get("responseMessage", ""),
        buttons=req.get("buttons") or [],
        media_files=req.get("media_files") or req.get("mediaFiles", []),
        is_active=req.get("is_active", req.get("isActive", True)),
        priority=int(req.get("priority", 0)),
        created_by=user.id,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return {"success": True, "data": model_to_dict(rule)}


@router.put("/auto-responder/{rule_id}")
def update_auto_responder_rule(
    rule_id: int,
    payload: AutoResponderUpdateRequest,
    user: User = Depends(require_organization),
    db: Session = Depends(get_db),
):
    rule = db.get(WhatsAppAutoResponder, rule_id)
    ensure_tenant_access(rule, user, "Auto Responder Rule")
    req = payload.to_payload()
    apply_payload(
        rule,
        req,
        {
            "triggerType": "trigger_type",
            "responseMessage": "response_message",
            "mediaFiles": "media_files",
            "isActive": "is_active",
        },
    )
    db.commit()
    return {"success": True, "data": model_to_dict(rule)}


@router.delete("/auto-responder/{rule_id}")
def delete_auto_responder_rule(
    rule_id: int,
    user: User = Depends(require_organization),
    db: Session = Depends(get_db),
):
    rule = db.get(WhatsAppAutoResponder, rule_id)
    ensure_tenant_access(rule, user, "Auto Responder Rule")
    db.delete(rule)
    db.commit()
    return {"success": True, "message": "Auto-responder rule deleted"}


@router.post("/auto-responder/test")
def test_auto_responder_endpoint(
    payload: AutoResponderTestRequest,
    user: User = Depends(require_organization),
    db: Session = Depends(get_db),
):
    req = payload.to_payload()
    message = req.get("message") or ""
    sender_phone = req.get("sender_phone") or req.get("senderPhone")
    result = evaluate_auto_responder(db, user, message, sender_phone)
    return {"success": True, "data": result}


# =====================================================================
# 4. GROUP TOOLS (Auto Joiner & Grab Members)
# =====================================================================
@router.post("/group-tools/parse-links")
def parse_group_links_endpoint(
    payload: GroupTaskCreateRequest,
    user: User = Depends(require_organization),
    db: Session = Depends(get_db),
):
    req = payload.to_payload()
    links = req.get("group_links") or req.get("groupLinks") or []
    if isinstance(links, str):
        links = links.splitlines()

    parsed = parse_group_links(links)
    
    # Save task log
    task = WhatsAppGroupTask(
        tenant_id=tenant_id_for_user(user),
        organization_id=user.organization_id,
        tenant_code=user.tenant_code,
        task_type="auto_join",
        title=req.get("title") or "Group Join Queue",
        extracted_count=len([p for p in parsed if p.get("is_valid")]),
        status="completed",
        details={"links": parsed},
        created_by=user.id,
    )
    db.add(task)
    db.commit()

    return {"success": True, "data": parsed, "task_id": task.id}


@router.post("/group-tools/grab-members")
def grab_members_endpoint(
    payload: GroupTaskCreateRequest,
    user: User = Depends(require_organization),
):
    req = payload.to_payload()
    raw_text = req.get("raw_text") or req.get("rawText") or ""
    prefix = req.get("default_country_code") or req.get("defaultCountryCode") or "+91"

    members = grab_members_from_text(raw_text, prefix)
    return {"success": True, "data": members, "count": len(members)}


@router.post("/group-tools/import-members")
def import_group_members_endpoint(
    payload: dict[str, Any],
    user: User = Depends(require_organization),
    db: Session = Depends(get_db),
):
    members = payload.get("members") or []
    group_name = payload.get("group_name") or payload.get("groupName") or "WhatsApp Group"

    t_id = tenant_id_for_user(user)
    org_id = user.organization_id
    t_code = user.tenant_code

    imported_count = 0
    skipped_count = 0

    for m in members:
        phone = m.get("phone")
        if not phone:
            continue

        existing = db.scalar(
            select(Customer).where(
                Customer.tenant_id == t_id,
                Customer.organization_id == org_id,
                Customer.phone == phone,
            )
        )
        if existing:
            skipped_count += 1
            continue

        cust = Customer(
            tenant_id=t_id,
            organization_id=org_id,
            tenant_code=t_code,
            name=m.get("name") or f"Group Contact {phone[-4:]}",
            phone=phone,
            whatsapp_number=phone,
            lifecycle={"segment": "leads", "status": "new"},
            source={"type": "group_grabber", "group_name": group_name},
            tags=["group-grabbed", f"group-{group_name.lower().replace(' ', '-')}"] ,
            is_active=True,
        )
        db.add(cust)
        imported_count += 1

    # Log task
    task = WhatsAppGroupTask(
        tenant_id=t_id,
        organization_id=org_id,
        tenant_code=t_code,
        task_type="grab_members",
        title=f"Grabbed from {group_name}",
        group_name=group_name,
        extracted_count=imported_count,
        status="completed",
        details={"total_submitted": len(members), "imported": imported_count, "skipped": skipped_count},
        created_by=user.id,
    )
    db.add(task)
    db.commit()

    return {
        "success": True,
        "imported_count": imported_count,
        "skipped_count": skipped_count,
        "message": f"Successfully imported {imported_count} group members as customers ({skipped_count} existing skipped).",
    }
