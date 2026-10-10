"""Normalized SaaS records. All business records carry tenant and organization scope."""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.connection import Base
from .common import TimestampMixin


def identifier():
    return uuid4().hex


class BusinessProfile(Base, TimestampMixin):
    __tablename__ = "business_profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False, unique=True)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    billing_email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(60))
    address: Mapped[dict] = mapped_column(JSONB, default=dict)
    tax_id: Mapped[str | None] = mapped_column(String(40))
    website: Mapped[str | None] = mapped_column(String(500))


class PlatformStaff(Base, TimestampMixin):
    __tablename__ = "platform_staff"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    permissions: Mapped[list] = mapped_column(JSONB, default=list)


class SubscriptionPlan(Base, TimestampMixin):
    __tablename__ = "subscription_plans"
    __table_args__ = (CheckConstraint("amount_minor > 0"), CheckConstraint("total_cycles > 0"))
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    interval: Mapped[str] = mapped_column(String(30), nullable=False)
    total_cycles: Mapped[int] = mapped_column(Integer, nullable=False)
    entitlements: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Subscription(Base, TimestampMixin):
    __tablename__ = "subscriptions"
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=identifier)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False, unique=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("subscription_plans.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="active")
    current_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)


class Invoice(Base, TimestampMixin):
    __tablename__ = "saas_invoices"
    __table_args__ = (CheckConstraint("amount_minor >= 0"),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=identifier)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    payment_reference: Mapped[str | None] = mapped_column(String(120), unique=True)
    invoice_reference: Mapped[str | None] = mapped_column(String(120))
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), default="subscription")
    status: Mapped[str] = mapped_column(String(30), default="paid")
    buyer_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    line_items: Mapped[list] = mapped_column(JSONB, default=list)


class UsageEntry(Base, TimestampMixin):
    __tablename__ = "usage_entries"
    __table_args__ = (UniqueConstraint("tenant_id", "external_reference"), CheckConstraint("amount_minor IS NULL OR amount_minor >= 0"))
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=identifier)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    external_reference: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    amount_minor: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str | None] = mapped_column(String(3))
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    period: Mapped[str | None] = mapped_column(String(80))


class ContactConsent(Base, TimestampMixin):
    __tablename__ = "contact_consents"
    __table_args__ = (UniqueConstraint("tenant_id", "organization_id", "phone"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    opted_in: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str | None] = mapped_column(String(80))
    evidence: Mapped[str | None] = mapped_column(Text)
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConsentEvent(Base):
    __tablename__ = "consent_events"
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=identifier)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    opted_in: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OnboardingRequest(Base, TimestampMixin):
    __tablename__ = "onboarding_requests"
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=identifier)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    phone: Mapped[str] = mapped_column(String(30), nullable=False)
    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="requested")
    customer_message: Mapped[str | None] = mapped_column(Text)
    provider_reference: Mapped[str | None] = mapped_column(String(255))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)


class MessageRecord(Base, TimestampMixin):
    __tablename__ = "message_records"
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=identifier)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    sender_phone_id: Mapped[str] = mapped_column(String(80), nullable=False)
    recipient: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    status_timestamp: Mapped[int] = mapped_column(Integer, default=0)
    bulk_job_id: Mapped[int | None] = mapped_column(ForeignKey("whatsapp_bulk_jobs.id"))


class CampaignOutbox(Base, TimestampMixin):
    __tablename__ = "campaign_outbox"
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=identifier)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    bulk_job_id: Mapped[int] = mapped_column(ForeignKey("whatsapp_bulk_jobs.id"), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=identifier)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(160))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
