"""Platform access comes from explicit staff membership, never a tenant role."""
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from uuid import UUID
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.connection import get_control_db
from app.models import Tenant, User, WhatsAppConnection
from app.models.saas import AuditEvent, OnboardingRequest, PlatformStaff, Subscription, SubscriptionPlan, UsageEntry
from app.services import billing
from app.services.audit import audit
from app.services.manual_subscriptions import operate, public_subscription
from app.services.security import get_current_user
from app.utils.helpers import model_to_dict

router = APIRouter()


def staff_permission(permission):
    def dependency(user: User = Depends(get_current_user), db: Session = Depends(get_control_db)):
        membership = db.get(PlatformStaff, user.id)
        if not membership or not membership.is_active or permission not in (membership.permissions or []):
            raise HTTPException(403, "Platform staff permission is required")
        return user
    return dependency


class PlanPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z0-9_-]{1,80}$")
    name: str = Field(min_length=1, max_length=255)
    amount_minor: int = Field(strict=True, gt=0)
    currency: str = Field(default="INR", pattern=r"^[A-Z]{3}$")
    interval: str = Field(pattern=r"^(daily|weekly|monthly|quarterly|yearly)$")
    total_cycles: int = Field(strict=True, ge=1, le=1000)
    whatsapp_numbers: int = Field(strict=True, ge=1, le=100)


class TenantPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_active: bool


class ManualPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: UUID
    reason: str = Field(min_length=1, max_length=500)


class AssignmentPayload(ManualPayload):
    plan_id: str = Field(min_length=1, max_length=80)
    current_start: AwareDatetime
    current_end: AwareDatetime

    @model_validator(mode="after")
    def valid_period(self):
        if self.current_start >= self.current_end:
            raise ValueError("Subscription start must precede expiry")
        self.current_start = self.current_start.astimezone(UTC)
        self.current_end = self.current_end.astimezone(UTC)
        return self


class RenewalPayload(ManualPayload):
    days: int = Field(strict=True, ge=1, le=3660)


class CancellationPayload(ManualPayload):
    at_period_end: StrictBool = True


@router.get("/subscriptions")
def subscriptions(user: User = Depends(staff_permission("subscriptions.read")), db: Session = Depends(get_control_db)):
    return {"success": True, "data": [public_subscription(row) for row in db.scalars(
        select(Subscription).order_by(Subscription.updated_at.desc()).limit(200))]}


@router.get("/organizations")
def subscription_organizations(user: User = Depends(staff_permission("subscriptions.read")), db: Session = Depends(get_control_db)):
    from app.models import Organization
    return {"success": True, "data": [{"id": row.id, "tenant_id": row.tenant_id, "name": row.name}
        for row in db.scalars(select(Organization).order_by(Organization.id).limit(200))]}


@router.get("/subscription-plans")
def subscription_plans(user: User = Depends(staff_permission("subscriptions.read")), db: Session = Depends(get_control_db)):
    return {"success": True, "data": [model_to_dict(row) for row in db.scalars(
        select(SubscriptionPlan).order_by(SubscriptionPlan.id))]}


@router.post("/tenants/{tenant_id}/organizations/{organization_id}/subscription/assign")
def assign_subscription(tenant_id: int, organization_id: int, payload: AssignmentPayload,
        user: User = Depends(staff_permission("subscriptions.manage")), db: Session = Depends(get_control_db)):
    return operate(db, user, tenant_id, organization_id, "assign", payload)


@router.post("/tenants/{tenant_id}/organizations/{organization_id}/subscription/renew")
def renew_subscription(tenant_id: int, organization_id: int, payload: RenewalPayload,
        user: User = Depends(staff_permission("subscriptions.manage")), db: Session = Depends(get_control_db)):
    return operate(db, user, tenant_id, organization_id, "renew", payload)


@router.post("/tenants/{tenant_id}/organizations/{organization_id}/subscription/cancel")
def cancel_subscription(tenant_id: int, organization_id: int, payload: CancellationPayload,
        user: User = Depends(staff_permission("subscriptions.manage")), db: Session = Depends(get_control_db)):
    return operate(db, user, tenant_id, organization_id, "cancel", payload)


class OnboardingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = Field(pattern=r"^(needs_customer_action|provider_review|billing_pending|ready|rejected)$")
    customer_message: str = Field(min_length=1, max_length=2000)
    provider_reference: str | None = Field(default=None, max_length=255)


class UsagePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: int = Field(gt=0)
    organization_id: int = Field(gt=0)
    external_reference: str = Field(min_length=1, max_length=160)
    category: str = Field(min_length=1, max_length=40)
    quantity: int = Field(gt=0)
    amount_minor: int = Field(ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    provider: str = Field(min_length=1, max_length=80)
    period: str = Field(min_length=1, max_length=80)


@router.get("/access")
def access(user: User = Depends(get_current_user), db: Session = Depends(get_control_db)):
    membership = db.get(PlatformStaff, user.id)
    return {"success": True, "data": {"is_staff": bool(membership and membership.is_active),
        "permissions": membership.permissions if membership and membership.is_active else []}}


@router.get("/overview")
def overview(user: User = Depends(staff_permission("tenants.read")), db: Session = Depends(get_control_db)):
    return {"success": True, "data": {"tenants": db.scalar(select(func.count()).select_from(Tenant)),
        "active_subscriptions": db.scalar(select(func.count()).select_from(Subscription).where(*billing.active_subscription_predicate(datetime.now(UTC)))),
        "pending_onboarding": db.scalar(select(func.count()).select_from(OnboardingRequest).where(OnboardingRequest.status != "ready"))}}


@router.get("/tenants")
def tenants(user: User = Depends(staff_permission("tenants.read")), db: Session = Depends(get_control_db)):
    return {"success": True, "data": [model_to_dict(row) for row in db.scalars(select(Tenant).order_by(Tenant.id.desc()).limit(200))]}


@router.patch("/tenants/{tenant_id}")
def update_tenant(tenant_id: int, payload: TenantPayload, user: User = Depends(staff_permission("tenants.manage")), db: Session = Depends(get_control_db)):
    row = db.get(Tenant, tenant_id)
    if not row:
        raise HTTPException(404, "Business not found")
    if tenant_id == user.tenant_id and not payload.is_active:
        raise HTTPException(400, "Staff cannot suspend their own business workspace")
    row.is_active = payload.is_active
    audit(db, user, "platform.tenant.status.updated", tenant_id, {"is_active": payload.is_active})
    db.commit()
    return {"success": True}


@router.get("/plans")
def plans(user: User = Depends(staff_permission("plans.manage")), db: Session = Depends(get_control_db)):
    return {"success": True, "data": [model_to_dict(row) for row in db.scalars(select(SubscriptionPlan))]}


@router.post("/plans")
def create_plan(payload: PlanPayload, user: User = Depends(staff_permission("plans.manage")), db: Session = Depends(get_control_db)):
    if db.get(SubscriptionPlan, payload.id):
        raise HTTPException(409, "Create a new plan version rather than changing existing subscription prices")
    row = SubscriptionPlan(id=payload.id, name=payload.name,
        amount_minor=payload.amount_minor, currency=payload.currency, interval=payload.interval,
        total_cycles=payload.total_cycles, entitlements={"whatsapp_numbers": payload.whatsapp_numbers})
    db.add(row)
    audit(db, user, "platform.plan.created", payload.id)
    db.commit()
    return {"success": True, "data": model_to_dict(row)}


@router.get("/onboarding")
def onboarding(user: User = Depends(staff_permission("onboarding.manage")), db: Session = Depends(get_control_db)):
    return {"success": True, "data": [model_to_dict(row) for row in db.scalars(select(OnboardingRequest).order_by(OnboardingRequest.created_at.desc()).limit(200))]}


@router.patch("/onboarding/{request_id}")
def update_onboarding(request_id: str, payload: OnboardingUpdate, user: User = Depends(staff_permission("onboarding.manage")), db: Session = Depends(get_control_db)):
    row = db.get(OnboardingRequest, request_id)
    if not row:
        raise HTTPException(404, "Onboarding request not found")
    if payload.status == "ready":
        connected = db.scalar(select(WhatsAppConnection).where(WhatsAppConnection.tenant_id == row.tenant_id, WhatsAppConnection.organization_id == row.organization_id))
        if not connected or not payload.provider_reference:
            raise HTTPException(409, "Customer authorization and a verified provider billing reference are required")
        if connected.token_expires_at and connected.token_expires_at <= datetime.now(UTC).replace(tzinfo=None):
            raise HTTPException(409, "The customer WhatsApp authorization has expired")
    row.status = payload.status
    row.customer_message = payload.customer_message
    row.provider_reference = payload.provider_reference
    audit(db, user, "platform.onboarding.updated", row.id, {"status": payload.status})
    db.commit()
    return {"success": True, "data": model_to_dict(row)}


@router.post("/usage")
def record_provider_usage(payload: UsagePayload, user: User = Depends(staff_permission("usage.manage")), db: Session = Depends(get_control_db)):
    from app.models import Organization
    organization = db.get(Organization, payload.organization_id)
    if not organization or organization.tenant_id != payload.tenant_id:
        raise HTTPException(404, "Business organization not found")
    existing = db.scalar(select(UsageEntry).where(UsageEntry.tenant_id == payload.tenant_id, UsageEntry.external_reference == payload.external_reference))
    if existing:
        if any(getattr(existing, key) != value for key, value in payload.model_dump().items()):
            raise HTTPException(409, "Provider usage reference conflicts with an existing entry")
        return {"success": True, "duplicate": True}
    row = UsageEntry(**payload.model_dump())
    db.add(row)
    audit(db, user, "platform.provider.usage.recorded", payload.external_reference, {"target_tenant": payload.tenant_id})
    db.commit()
    return {"success": True, "data": model_to_dict(row)}


@router.get("/audit")
def events(user: User = Depends(staff_permission("audit.read")), db: Session = Depends(get_control_db)):
    return {"success": True, "data": [model_to_dict(row) for row in db.scalars(select(AuditEvent).order_by(AuditEvent.occurred_at.desc()).limit(200))]}
