from sqlalchemy import Boolean, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.connection import Base

from .common import TimestampMixin


class WhatsAppTemplate(Base, TimestampMixin):
    __tablename__ = "whatsapp_templates"
    __table_args__ = (Index("ix_whatsapp_templates_tenant_org", "tenant_id", "organization_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True, nullable=False)
    organization_id: Mapped[int] = mapped_column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    tenant_code: Mapped[str | None] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    whatsapp_template_name: Mapped[str | None] = mapped_column(String(255))
    content: Mapped[dict] = mapped_column(JSONB, default=dict)
    variables: Mapped[list] = mapped_column(JSONB, default=list)
    targeting: Mapped[dict] = mapped_column(JSONB, default=dict)
    stats: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
