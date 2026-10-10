from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models import Organization, User
from app.models.saas import BusinessProfile, ContactConsent, Invoice, MessageRecord, OnboardingRequest, SubscriptionPlan, UsageEntry
from app.services import billing
from app.services.audit import audit
from app.services.manual_subscriptions import public_subscription
from app.services.consent import set_consent
from app.services.security import require_organization, require_owner, require_module
from app.utils.helpers import model_to_dict

router = APIRouter()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProfilePayload(StrictModel):
    legal_name: str = Field(min_length=1, max_length=255)
    billing_email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=60)
    address: dict = Field(default_factory=dict)
    tax_id: str | None = Field(default=None, max_length=40)
    website: str | None = Field(default=None, max_length=500)


class ConsentPayload(StrictModel):
    phone: str = Field(min_length=8, max_length=30)
    opted_in: bool
    source: str = Field(min_length=1, max_length=80)
    evidence: str | None = Field(default=None, max_length=2000)


class OnboardingPayload(StrictModel):
    phone: str = Field(min_length=8, max_length=30)
    business_name: str = Field(min_length=1, max_length=255)


def scoped(model, user):
    return select(model).where(model.tenant_id == user.tenant_id, model.organization_id == user.organization_id)


@router.get("/profile")
def profile(user: User = Depends(require_organization), db: Session = Depends(get_db)):
    row = db.scalar(scoped(BusinessProfile, user))
    return {"success": True, "data": model_to_dict(row) if row else None}


@router.put("/profile")
def update_profile(payload: ProfilePayload, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    db.scalar(select(Organization).where(Organization.id == user.organization_id).with_for_update())
    row = db.scalar(scoped(BusinessProfile, user))
    if not row:
        row = BusinessProfile(tenant_id=user.tenant_id, organization_id=user.organization_id)
        db.add(row)
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    audit(db, user, "business.profile.updated")
    db.commit()
    return {"success": True, "data": model_to_dict(row)}


@router.get("/plans")
def plans(user: User = Depends(require_organization), db: Session = Depends(get_db)):
    rows = db.scalars(select(SubscriptionPlan).where(SubscriptionPlan.is_active.is_(True))).all()
    return {"success": True, "data": [{"id": row.id, "name": row.name, "amount_minor": row.amount_minor,
        "currency": row.currency, "interval": row.interval, "entitlements": row.entitlements} for row in rows]}


@router.get("/subscription")
def subscription(user: User = Depends(require_organization), db: Session = Depends(get_db)):
    row = billing.subscription_for(db, user)
    return {"success": True, "data": public_subscription(row)}


@router.get("/invoices")
def invoices(user: User = Depends(require_owner), db: Session = Depends(get_db)):
    return {"success": True, "data": [model_to_dict(row) for row in db.scalars(scoped(Invoice, user).order_by(Invoice.created_at.desc()).limit(200))]}


@router.get("/usage")
def usage(user: User = Depends(require_owner), db: Session = Depends(get_db)):
    return {"success": True, "data": [model_to_dict(row) for row in db.scalars(scoped(UsageEntry, user).order_by(UsageEntry.created_at.desc()).limit(500))],
        "message_count": db.scalar(select(func.count()).select_from(MessageRecord).where(MessageRecord.tenant_id == user.tenant_id, MessageRecord.organization_id == user.organization_id)),
        "billing_note": "Messaging usage charges are separate from your SaaS subscription. Only reconciled provider usage is billable."}


@router.get("/consents")
def consents(user: User = Depends(require_module("customers", "whatsapp")), db: Session = Depends(get_db)):
    return {"success": True, "data": [model_to_dict(row) for row in db.scalars(scoped(ContactConsent, user).order_by(ContactConsent.updated_at.desc()).limit(200))]}


@router.post("/consents")
def update_consent(payload: ConsentPayload, user: User = Depends(require_module("customers", "whatsapp")), db: Session = Depends(get_db)):
    set_consent(db, user.tenant_id, user.organization_id, payload.phone, payload.opted_in, payload.source, payload.evidence, user.id)
    audit(db, user, "contact.consent.updated", details={"opted_in": payload.opted_in, "source": payload.source})
    db.commit()
    return {"success": True}


@router.get("/onboarding")
def onboarding(user: User = Depends(require_owner), db: Session = Depends(get_db)):
    return {"success": True, "data": [model_to_dict(row) for row in db.scalars(scoped(OnboardingRequest, user).order_by(OnboardingRequest.created_at.desc()).limit(100))]}


@router.post("/onboarding")
def request_onboarding(payload: OnboardingPayload, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    billing.require_paid_subscription(db, user)
    from app.services.meta_whatsapp import normalize_phone
    row = OnboardingRequest(tenant_id=user.tenant_id, organization_id=user.organization_id,
        phone=normalize_phone(payload.phone), business_name=payload.business_name, created_by=user.id)
    db.add(row)
    db.flush()
    audit(db, user, "whatsapp.onboarding.requested", row.id)
    db.commit()
    return {"success": True, "data": model_to_dict(row)}


@router.get("/messages")
def messages(user: User = Depends(require_module("whatsapp")), db: Session = Depends(get_db)):
    return {"success": True, "data": [model_to_dict(row) for row in db.scalars(scoped(MessageRecord, user).order_by(MessageRecord.created_at.desc()).limit(200))]}
