import re
import urllib.request
import urllib.parse
import json
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer, GoogleMapsLead, User
from app.services.security import tenant_id_for_user


def search_google_maps_leads(query: str, location: str, limit: int = 25) -> list[dict[str, Any]]:
    """Return only real OpenStreetMap records; never fabricate contact data."""
    from fastapi import HTTPException
    if not 1 <= limit <= 50:
        raise HTTPException(400, "Search limit must be between 1 and 50")
    search_term = urllib.parse.quote(f"{query.strip()} in {location.strip()}")
    request = urllib.request.Request(
        f"https://nominatim.openstreetmap.org/search?q={search_term}&format=json&addressdetails=1&extratags=1&limit={limit}",
        headers={"User-Agent": "HanuRamTech/1.0 (hanuramtech@gmail.com)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            items = json.loads(response.read(2_000_000))
    except (OSError, ValueError):
        raise HTTPException(502, "Live directory search is unavailable; no generated leads were substituted") from None
    if not isinstance(items, list):
        raise HTTPException(502, "Unexpected directory response")
    leads = []
    for item in items:
        tags = item.get("extratags") or {}
        phone = tags.get("phone") or tags.get("contact:phone") or tags.get("contact:mobile")
        leads.append({
            "id": f"osm_{item.get('osm_type')}_{item.get('osm_id')}",
            "business_name": item.get("name") or item.get("display_name", "").split(",")[0],
            "phone": re.sub(r"[^\d+]", "", phone) if phone else None,
            "category": item.get("type") or query,
            "rating": None, "reviews_count": None,
            "address": item.get("display_name"),
            "website": tags.get("website") or tags.get("contact:website"),
            "latitude": item.get("lat"), "longitude": item.get("lon"),
            "verified": False, "source": "OpenStreetMap",
        })
    return leads


def import_gmaps_leads_to_customers(
    db: Session,
    user: User,
    leads: list[dict[str, Any]],
    tag: str | None = None,
) -> dict[str, Any]:
    """
    Imports extracted Google Maps business leads directly into the Customer table.
    Enforces strict multi-tenant isolation.
    """
    t_id = tenant_id_for_user(user)
    org_id = user.organization_id
    t_code = user.tenant_code

    imported_count = 0
    duplicate_count = 0

    custom_tag = tag or "gmaps-lead"

    for lead in leads:
        raw_phone = lead.get("phone") or ""
        clean_phone = re.sub(r"[^\d+]", "", raw_phone)
        if not clean_phone:
            continue

        biz_name = lead.get("business_name") or "Business Lead"

        # Check if customer with this phone already exists for this tenant
        existing = db.scalar(
            select(Customer).where(
                Customer.tenant_id == t_id,
                Customer.organization_id == org_id,
                Customer.phone == clean_phone,
            )
        )
        if existing:
            duplicate_count += 1
            continue

        customer = Customer(
            tenant_id=t_id,
            organization_id=org_id,
            tenant_code=t_code,
            name=biz_name,
            phone=clean_phone,
            whatsapp_number=clean_phone,
            address=lead.get("address"),
            demographics={
                "city": lead.get("location") or "Local Area",
                "website": lead.get("website"),
                "rating": lead.get("rating"),
            },
            lifecycle={
                "segment": "lead",
                "status": "new",
                "source": "google_maps",
            },
            source={
                "type": "gmaps_extractor",
                "category": lead.get("category"),
                "reviews_count": lead.get("reviews_count"),
            },
            tags=["gmaps-lead", custom_tag, (lead.get("category") or "business").lower().replace(" ", "-")],
            is_active=True,
        )
        db.add(customer)
        db.flush()

        # Save to GoogleMapsLead log table
        lead_record = GoogleMapsLead(
            tenant_id=t_id,
            organization_id=org_id,
            tenant_code=t_code,
            search_query=lead.get("category") or "General",
            location=lead.get("location") or "City",
            business_name=biz_name,
            phone=clean_phone,
            category=lead.get("category"),
            rating=str(lead.get("rating") or ""),
            reviews_count=int(lead.get("reviews_count") or 0),
            address=lead.get("address"),
            website=lead.get("website"),
            is_imported=True,
            customer_id=customer.id,
            raw_data=lead,
        )
        db.add(lead_record)
        imported_count += 1

    db.commit()

    return {
        "success": True,
        "imported_count": imported_count,
        "duplicate_count": duplicate_count,
        "total_processed": len(leads),
        "message": f"Successfully imported {imported_count} leads into Customers ({duplicate_count} existing skipped).",
    }
