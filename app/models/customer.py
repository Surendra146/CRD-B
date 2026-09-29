from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.connection import Base

from .common import TimestampMixin


class Customer(Base, TimestampMixin):
    __tablename__ = "customers"
    __table_args__ = (
        Index("ix_customers_tenant_org", "tenant_id", "organization_id"),
        Index("ix_customers_tenant_phone", "tenant_id", "phone"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True, nullable=False)
    organization_id: Mapped[int] = mapped_column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    tenant_code: Mapped[str | None] = mapped_column(String(80), index=True)
    external_id: Mapped[str | None] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    phone: Mapped[str | None] = mapped_column(String(60), index=True)
    whatsapp_number: Mapped[str | None] = mapped_column(String(60))
    address: Mapped[str | None] = mapped_column(Text)
    customer_created_date: Mapped[datetime | None] = mapped_column(DateTime)
    demographics: Mapped[dict] = mapped_column(JSONB, default=dict)
    lifecycle: Mapped[dict] = mapped_column(JSONB, default=dict)
    purchases: Mapped[list] = mapped_column(JSONB, default=list)
    interactions: Mapped[list] = mapped_column(JSONB, default=list)
    follow_up: Mapped[dict] = mapped_column(JSONB, default=dict)
    preferences: Mapped[dict] = mapped_column(JSONB, default=dict)
    tags: Mapped[list] = mapped_column(JSONB, default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    source: Mapped[dict] = mapped_column(JSONB, default=dict)
    module_tags: Mapped[list] = mapped_column(JSONB, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
