from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.connection import Base
from .common import TimestampMixin


class WhatsAppBulkJob(Base, TimestampMixin):
    __tablename__ = "whatsapp_bulk_jobs"
    __table_args__ = (
        Index("ix_whatsapp_bulk_jobs_tenant_org", "tenant_id", "organization_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True, nullable=False)
    organization_id: Mapped[int] = mapped_column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    tenant_code: Mapped[str | None] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    audience_type: Mapped[str] = mapped_column(String(80), default="segment")
    audience_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    message_template: Mapped[str] = mapped_column(Text, nullable=False)
    buttons: Mapped[list] = mapped_column(JSONB, default=list)
    media_files: Mapped[list] = mapped_column(JSONB, default=list)
    batch_delay_seconds: Mapped[int] = mapped_column(Integer, default=5)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(80), default="completed", index=True)
    stats: Mapped[dict] = mapped_column(JSONB, default=dict)
    recipients_summary: Mapped[list] = mapped_column(JSONB, default=list)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class WhatsAppAutoResponder(Base, TimestampMixin):
    __tablename__ = "whatsapp_auto_responders"
    __table_args__ = (
        Index("ix_whatsapp_auto_responders_tenant_org", "tenant_id", "organization_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True, nullable=False)
    organization_id: Mapped[int] = mapped_column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    tenant_code: Mapped[str | None] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(80), default="contains")
    keywords: Mapped[list] = mapped_column(JSONB, default=list)
    response_message: Mapped[str] = mapped_column(Text, nullable=False)
    buttons: Mapped[list] = mapped_column(JSONB, default=list)
    media_files: Mapped[list] = mapped_column(JSONB, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    match_count: Mapped[int] = mapped_column(Integer, default=0)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class GoogleMapsLead(Base, TimestampMixin):
    __tablename__ = "gmaps_extracted_leads"
    __table_args__ = (
        Index("ix_gmaps_leads_tenant_org", "tenant_id", "organization_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True, nullable=False)
    organization_id: Mapped[int] = mapped_column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    tenant_code: Mapped[str | None] = mapped_column(String(80), index=True)
    search_query: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(80), index=True)
    category: Mapped[str | None] = mapped_column(String(120))
    rating: Mapped[str | None] = mapped_column(String(40))
    reviews_count: Mapped[int] = mapped_column(Integer, default=0)
    address: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(String(255))
    is_imported: Mapped[bool] = mapped_column(Boolean, default=False)
    customer_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("customers.id"))
    raw_data: Mapped[dict] = mapped_column(JSONB, default=dict)


class WhatsAppGroupTask(Base, TimestampMixin):
    __tablename__ = "whatsapp_group_tasks"
    __table_args__ = (
        Index("ix_whatsapp_group_tasks_tenant_org", "tenant_id", "organization_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True, nullable=False)
    organization_id: Mapped[int] = mapped_column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    tenant_code: Mapped[str | None] = mapped_column(String(80), index=True)
    task_type: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    group_name: Mapped[str | None] = mapped_column(String(255))
    extracted_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(80), default="completed")
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
