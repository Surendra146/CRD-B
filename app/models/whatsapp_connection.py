from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.connection import Base
from .common import TimestampMixin


class WhatsAppConnection(Base, TimestampMixin):
    __tablename__ = "whatsapp_connections"
    __table_args__ = (UniqueConstraint("organization_id"), UniqueConstraint("phone_number_id"))

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    waba_id: Mapped[str] = mapped_column(String(80), nullable=False)
    phone_number_id: Mapped[str] = mapped_column(String(80), nullable=False)
    display_phone_number: Mapped[str | None] = mapped_column(String(80))
    verified_name: Mapped[str | None] = mapped_column(String(255))
    encrypted_access_token: Mapped[str] = mapped_column(Text, nullable=False)
    connected_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime)


class WhatsAppSignupAttempt(Base):
    __tablename__ = "whatsapp_signup_attempts"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    encrypted_access_token: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    phase: Mapped[str] = mapped_column(String(30), default="started", nullable=False)
