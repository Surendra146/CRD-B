from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.services.crud import apply_payload, paginate, search_like
from app.database.connection import get_db
from app.utils.helpers import apply_customer_purchase_metrics, day_bounds, model_to_dict, normalize_phone, normalize_text
from app.models import Customer, User
from app.schemas.customer import BulkStatusUpdateRequest, CustomerCreateRequest, CustomerUpdateRequest, InteractionRequest, PurchaseRequest
from app.services.security import require_organization



def get_customers(
    page: int = 1,
    limit: int = 20,
    moduleType: str | None = None,
    status: str | None = None,
    segment: str | None = None,
    search: str | None = None,
    sortBy: str = "created_at",
    sortOrder: str = "desc",
    user: User = Depends(require_organization),
    db: Session = Depends(get_db),
):
    statement = select(Customer).where(Customer.organization_id == user.organization_id)
    if moduleType:
        statement = statement.where(Customer.module_tags.contains([moduleType]))
    if status:
        statement = statement.where(Customer.lifecycle["status"].as_string() == status)
    if segment:
        statement = statement.where(Customer.lifecycle["segment"].as_string() == segment)
    statement = search_like(statement, Customer, search or "", ["external_id", "name", "email", "phone", "address"])
    sort_column = getattr(Customer, sortBy, Customer.created_at)
    statement = statement.order_by(sort_column.asc() if sortOrder == "asc" else sort_column.desc())
    return paginate(db, statement, page, limit)


def get_customer(customer_id: int, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    customer = db.get(Customer, customer_id)
    if not customer or customer.organization_id != user.organization_id:
        raise HTTPException(404, "Customer not found")
    return {"success": True, "data": model_to_dict(customer)}


def create_customer(payload: CustomerCreateRequest, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    payload = payload.to_payload()
    for field, label in {
        "externalId": "Customer Code",
        "name": "Customer Name",
        "phone": "Phone Number",
        "address": "Address",
        "customerCreatedDate": "Customer Created Date",
    }.items():
        if not str(payload.get(field, "")).strip():
            raise HTTPException(400, f"{label} is required")
    bounds = day_bounds(payload.get("customerCreatedDate"))
    if not bounds:
        raise HTTPException(400, "Customer Created Date is invalid")
    phone = normalize_phone(payload.get("phone"))
    duplicates = db.scalars(
        select(Customer).where(
            Customer.organization_id == user.organization_id,
            Customer.phone == phone,
            Customer.customer_created_date >= bounds[0],
            Customer.customer_created_date < bounds[1],
        )
    ).all()
    if any(normalize_text(item.name) == normalize_text(payload.get("name")) and normalize_text(item.address) == normalize_text(payload.get("address")) for item in duplicates):
        raise HTTPException(409, "Customer already created.")
    module_tag = payload.get("moduleType") or "customer_details"
    customer = Customer(
        organization_id=user.organization_id,
        tenant_code=user.tenant_code,
        external_id=payload.get("externalId"),
        name=payload.get("name"),
        email=payload.get("email"),
        phone=phone,
        whatsapp_number=payload.get("whatsappNumber"),
        address=payload.get("address"),
        customer_created_date=bounds[0],
        demographics=payload.get("demographics") or {},
        lifecycle=payload.get("lifecycle") or {"status": "new"},
        preferences=payload.get("preferences") or {"preferredChannel": "whatsapp", "marketingOptIn": True, "language": "en"},
        tags=payload.get("tags") or [],
        notes=payload.get("notes"),
        source={"type": "manual", "importedAt": datetime.utcnow().isoformat()},
        module_tags=[module_tag]
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return {"success": True, "data": model_to_dict(customer)}


def update_customer(customer_id: int, payload: CustomerUpdateRequest, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    payload = payload.to_payload()
    customer = db.get(Customer, customer_id)
    if not customer or customer.organization_id != user.organization_id:
        raise HTTPException(404, "Customer not found")
    apply_payload(
        customer,
        payload,
        {"externalId": "external_id", "whatsappNumber": "whatsapp_number", "customerCreatedDate": "customer_created_date", "moduleTags": "module_tags"},
    )
    if "phone" in payload:
        customer.phone = normalize_phone(payload["phone"])
    db.commit()
    return {"success": True, "data": model_to_dict(customer)}


def delete_customer(customer_id: int, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    customer = db.get(Customer, customer_id)
    if not customer or customer.organization_id != user.organization_id:
        raise HTTPException(404, "Customer not found")
    db.delete(customer)
    db.commit()
    return {"success": True, "message": "Customer deleted"}


def add_purchase(customer_id: int, payload: PurchaseRequest, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    payload = payload.to_payload()
    customer = db.get(Customer, customer_id)
    if not customer or customer.organization_id != user.organization_id:
        raise HTTPException(404, "Customer not found")
    customer.purchases = [*(customer.purchases or []), payload]
    apply_customer_purchase_metrics(customer)
    db.commit()
    return {"success": True, "data": model_to_dict(customer)}


def add_interaction(customer_id: int, payload: InteractionRequest, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    payload = payload.to_payload()
    customer = db.get(Customer, customer_id)
    if not customer or customer.organization_id != user.organization_id:
        raise HTTPException(404, "Customer not found")
    interaction = {**payload, "createdBy": user.id, "createdAt": datetime.utcnow().isoformat()}
    customer.interactions = [*(customer.interactions or []), interaction]
    db.commit()
    return {"success": True, "data": model_to_dict(customer)}


def get_timeline(customer_id: int, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    customer = db.get(Customer, customer_id)
    if not customer or customer.organization_id != user.organization_id:
        raise HTTPException(404, "Customer not found")
    timeline = [
        *[{"type": "purchase", "date": item.get("date"), "data": item} for item in (customer.purchases or [])],
        *[{"type": "interaction", "date": item.get("createdAt"), "data": item} for item in (customer.interactions or [])],
    ]
    timeline.sort(key=lambda item: str(item.get("date") or ""), reverse=True)
    return {"success": True, "data": timeline}


def bulk_update_status(payload: BulkStatusUpdateRequest, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    payload = payload.to_payload()
    customer_ids = payload.get("customerIds") or []
    updated = 0
    for customer in db.scalars(select(Customer).where(Customer.id.in_(customer_ids), Customer.organization_id == user.organization_id)):
        lifecycle = customer.lifecycle or {}
        lifecycle["status"] = payload.get("status")
        customer.lifecycle = lifecycle
        updated += 1
    db.commit()
    return {"success": True, "message": f"Updated {updated} customers"}


router = APIRouter(dependencies=[Depends(require_organization)])

router.get("/")(get_customers)
router.get("/{customer_id}")(get_customer)
router.post("/")(create_customer)
router.put("/{customer_id}")(update_customer)
router.delete("/{customer_id}")(delete_customer)
router.post("/{customer_id}/purchases")(add_purchase)
router.post("/{customer_id}/interactions")(add_interaction)
router.get("/{customer_id}/timeline")(get_timeline)
router.post("/bulk-update-status")(bulk_update_status)




