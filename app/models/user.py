from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.connection import Base

from .common import TimestampMixin
from .organization import Organization


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(60))
    phone_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    phone_otp_hash: Mapped[str | None] = mapped_column(String(255))
    phone_otp_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    company: Mapped[dict] = mapped_column(JSONB, default=dict)
    role: Mapped[str] = mapped_column(String(80), default="owner")
    role_profile_name: Mapped[str | None] = mapped_column(String(255))
    allowed_modules: Mapped[list] = mapped_column(JSONB, default=list)
    organization_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("organizations.id"), index=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    tenant_code: Mapped[str | None] = mapped_column(String(80), index=True)
    subscription: Mapped[dict] = mapped_column(JSONB, default=dict)
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login: Mapped[datetime | None] = mapped_column(DateTime)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime)
    password_reset_token: Mapped[str | None] = mapped_column(String(255))
    password_reset_expires: Mapped[datetime | None] = mapped_column(DateTime)

    organization: Mapped[Organization | None] = relationship(foreign_keys=[organization_id])
