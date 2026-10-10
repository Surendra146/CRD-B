"""Provider-independent subscription access and entitlements."""
from datetime import UTC, datetime
from fastapi import HTTPException
from sqlalchemy import select
from app.models.saas import Subscription, SubscriptionPlan


def subscription_for(db, user, lock=False):
    statement = select(Subscription).where(Subscription.tenant_id == user.tenant_id, Subscription.organization_id == user.organization_id)
    return db.scalar(statement.with_for_update() if lock else statement)


def require_paid_subscription(db, user):
    # Keep the helper name used by existing WhatsApp/CRM consumers.
    row = subscription_for(db, user)
    if effective_status(row) != "active":
        raise HTTPException(402, "An active subscription is required")
    return row


def number_limit(db, user):
    row = require_paid_subscription(db, user)
    plan = db.get(SubscriptionPlan, row.plan_id)
    value = (plan.entitlements or {}).get("whatsapp_numbers") if plan else None
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise HTTPException(403, "This subscription does not include WhatsApp numbers")
    return value
def utc(value):
    return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value


def effective_status(row, now=None):
    if not row:
        return None
    if row.status != "active":
        return row.status
    now = now or datetime.now(UTC)
    start, end = utc(row.current_start), utc(row.current_end)
    if not start or not end or end <= now:
        return "expired"
    if start > now:
        return "scheduled"
    return "active"


def active_subscription_predicate(now):
    return (Subscription.status == "active", Subscription.current_start <= now,
            Subscription.current_end > now)
