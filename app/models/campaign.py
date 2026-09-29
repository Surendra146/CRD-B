from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.connection import Base

from .common import TimestampMixin


class Campaign(Base, TimestampMixin):
    __tablename__ = "campaigns"
    __table_args__ = (Index("ix_campaigns_tenant_org", "tenant_id", "organization_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True, nullable=False)
    organization_id: Mapped[int] = mapped_column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    tenant_code: Mapped[str | None] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(80), nullable=False)
    trigger: Mapped[dict] = mapped_column(JSONB, default=dict)
    template_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("whatsapp_templates.id"), index=True)
    audience: Mapped[dict] = mapped_column(JSONB, default=dict)
    schedule: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(80), default="draft", index=True)
    stats: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime)
