"""Staff operations serialized per organization, with atomic audit and retry safety."""
import hashlib
import json
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select

from app.models import Organization, Tenant
from app.models.saas import AuditEvent, Subscription, SubscriptionPlan
from app.services.audit import audit
from app.services.billing import effective_status, utc
from app.utils.helpers import model_to_dict


def public_subscription(row):
    return {**model_to_dict(row), "effective_status": effective_status(row)} if row else None


def operate(db, actor, tenant_id, organization_id, operation, payload):
    # Lock even when no subscription exists to serialize first assignments/retries.
    organization = db.scalar(select(Organization).where(Organization.id == organization_id,
        Organization.tenant_id == tenant_id).with_for_update())
    if not organization:
        raise HTTPException(404, "Business organization not found")
    request_id = str(payload.request_id)
    values = payload.model_dump(mode="json")
    fingerprint = hashlib.sha256(json.dumps({"operation": operation, "payload": values},
        sort_keys=True).encode()).hexdigest()
    previous = db.scalar(select(AuditEvent).where(
        AuditEvent.resource_id == f"organization:{organization_id}",
        AuditEvent.action.like("platform.subscription.%"),
        AuditEvent.details["request_id"].astext == request_id))
    if previous:
        if previous.actor_id != actor.id or previous.details["fingerprint"] != fingerprint:
            raise HTTPException(409, "Request ID conflicts with an existing subscription operation")
        return {"success": True, "duplicate": True, "data": previous.details["after"]}
    row = db.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id,
        Subscription.organization_id == organization_id).with_for_update())
    before = public_subscription(row)
    now = datetime.now(UTC)
    if operation == "assign":
        tenant = db.get(Tenant, tenant_id)
        plan = db.get(SubscriptionPlan, payload.plan_id)
        if not tenant or not tenant.is_active:
            raise HTTPException(409, "Cannot assign a subscription to a suspended business")
        if not plan or not plan.is_active:
            raise HTTPException(404, "Active subscription plan not found")
        if payload.current_end <= now:
            raise HTTPException(422, "Assignment expiry must be in the future")
        if not row:
            row = Subscription(tenant_id=tenant_id, organization_id=organization_id)
            db.add(row)
        row.plan_id = plan.id
        row.current_start, row.current_end = payload.current_start, payload.current_end
        row.status, row.cancel_at_period_end = "active", False
    elif operation == "renew":
        if not row:
            raise HTTPException(404, "Subscription not found")
        tenant = db.get(Tenant, tenant_id)
        if not tenant or not tenant.is_active:
            raise HTTPException(409, "Cannot renew a subscription for a suspended business")
        if row.status not in {"active", "expired", "completed"}:
            raise HTTPException(409, "Assign a plan to reactivate this subscription")
        end = utc(row.current_end)
        if not end or not row.current_start or utc(row.current_start) >= end:
            raise HTTPException(409, "Assign a valid subscription period before renewing")
        if end <= now:
            row.current_start = now
        row.current_end = max(end, now) + timedelta(days=payload.days)
        row.status, row.cancel_at_period_end = "active", False
    elif operation == "cancel":
        if not row:
            raise HTTPException(404, "Subscription not found")
        if payload.at_period_end:
            if row.status != "active" or not row.current_end or utc(row.current_end) <= now:
                raise HTTPException(409, "A current subscription period is required")
            row.cancel_at_period_end = True
        else:
            row.status, row.cancel_at_period_end = "cancelled", False
    else:
        raise ValueError("Unknown manual subscription operation")
    db.flush()
    after = public_subscription(row)
    audit(db, actor, f"platform.subscription.{operation}", f"organization:{organization_id}", {
        "target_tenant": tenant_id, "target_organization": organization_id,
        "request_id": request_id, "fingerprint": fingerprint, "reason": payload.reason,
        "before": before, "after": after})
    db.commit()
    return {"success": True, "data": after}
