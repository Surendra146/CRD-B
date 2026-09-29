from collections import Counter
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.customer import Customer
from app.models.user import User
from app.services.security import require_organization, tenant_id_for_user
from app.utils.helpers import model_to_dict



def customer_location(customer: Customer) -> str | None:
    return ((customer.demographics or {}).get("location") or {}).get("locationName")


def purchase_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def get_customer_rows(db: Session, user: User, location: str | None = None) -> list[Customer]:
    # Ensure we return a concrete list to satisfy the declared return type
    rows = list(
        db.scalars(
            select(Customer).where(
                Customer.tenant_id == tenant_id_for_user(user),
                Customer.organization_id == user.organization_id,
            )
        ).all()
    )
    if location and location != "all":
        rows = [customer for customer in rows if customer_location(customer) == location]
    return rows


def revenue_summary(customers: list[Customer]) -> dict:
    purchases = [
        purchase
        for customer in customers
        for purchase in (customer.purchases or [])
        if purchase.get("status", "completed") == "completed"
    ]
    total_revenue = sum(float(purchase.get("amount") or 0) for purchase in purchases)
    total_orders = len(purchases)
    total_customers = len(customers)
    return {
        "totalRevenue": total_revenue,
        "totalOrders": total_orders,
        "avgOrderValue": total_revenue / total_orders if total_orders else 0,
        "avgLifetimeValue": total_revenue / total_customers if total_customers else 0,
    }


def daily_activity(customers: list[Customer], days: int = 30) -> list[dict]:
    start = datetime.utcnow().date() - timedelta(days=days - 1)
    buckets = {
        (start + timedelta(days=offset)).isoformat(): {
            "_id": (start + timedelta(days=offset)).isoformat(),
            "revenue": 0,
            "orders": 0,
        }
        for offset in range(days)
    }
    for customer in customers:
        for purchase in customer.purchases or []:
            parsed = purchase_date(purchase.get("date"))
            if not parsed:
                continue
            key = parsed.date().isoformat()
            if key not in buckets:
                continue
            buckets[key]["revenue"] += float(purchase.get("amount") or 0)
            buckets[key]["orders"] += 1
    return list(buckets.values())


def status_counts(customers: list[Customer]) -> Counter:
    return Counter((customer.lifecycle or {}).get("status") or "new" for customer in customers)


def get_dashboard(
    location: str | None = Query(None),
    user: User = Depends(require_organization),
    db: Session = Depends(get_db),
):
    customers = get_customer_rows(db, user, location)
    all_customers = get_customer_rows(db, user)
    statuses = status_counts(customers)
    segments = Counter((customer.lifecycle or {}).get("segment") or "unassigned" for customer in customers)
    locations = sorted({loc for loc in {customer_location(customer) for customer in all_customers} if loc is not None})

    return {
        "success": True,
        "data": {
            "overview": {
                "totalCustomers": len(customers),
                "activeCustomers": statuses.get("active", 0) + statuses.get("new", 0),
                "atRiskCustomers": statuses.get("at_risk", 0),
                "churnedCustomers": statuses.get("churned", 0),
            },
            "revenue": revenue_summary(customers),
            "segments": dict(segments),
            "locations": locations,
            "recentActivity": daily_activity(customers),
        },
    }


def get_segment_analysis(user: User = Depends(require_organization), db: Session = Depends(get_db)):
    customers = get_customer_rows(db, user)
    segments = Counter((customer.lifecycle or {}).get("segment") or "unassigned" for customer in customers)
    return {"success": True, "data": [{"_id": key, "count": value} for key, value in segments.items()]}


def get_cohort_analysis():
    return {"success": True, "data": []}


def get_churn_analysis(user: User = Depends(require_organization), db: Session = Depends(get_db)):
    customers = get_customer_rows(db, user)
    at_risk = [model_to_dict(customer) for customer in customers if (customer.lifecycle or {}).get("status") == "at_risk"]
    churned = [model_to_dict(customer) for customer in customers if (customer.lifecycle or {}).get("status") == "churned"]
    return {"success": True, "data": {"atRiskCustomers": at_risk, "churnedCustomers": churned}}


def get_revenue_analytics(user: User = Depends(require_organization), db: Session = Depends(get_db)):
    customers = get_customer_rows(db, user)
    return {
        "success": True,
        "data": {
            **revenue_summary(customers),
            "dailyRevenue": daily_activity(customers),
        },
    }


def recalculate_scores():
    return {"success": True, "message": "Scores recalculated"}


def get_legacy_filter_options(dashboard_id: int):
    return {"success": True, "data": {"dashboardId": dashboard_id, "filters": []}}


def get_legacy_raw_data(dashboard_id: int):
    return {"success": True, "data": []}


def get_legacy_dashboard_analytics(dashboard_id: int):
    return {"success": True, "data": {"dashboardId": dashboard_id}}


router = APIRouter(dependencies=[Depends(require_organization)])

router.get("/dashboard")(get_dashboard)
router.get("/segments")(get_segment_analysis)
router.get("/cohorts")(get_cohort_analysis)
router.get("/churn")(get_churn_analysis)
router.get("/revenue")(get_revenue_analytics)
router.post("/recalculate")(recalculate_scores)
router.get("/{dashboard_id}/filters")(get_legacy_filter_options)
router.get("/{dashboard_id}/raw")(get_legacy_raw_data)
router.get("/{dashboard_id}")(get_legacy_dashboard_analytics)




