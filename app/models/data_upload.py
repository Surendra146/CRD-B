from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.connection import Base

from .common import TimestampMixin


class DataUpload(Base, TimestampMixin):
    __tablename__ = "data_uploads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    tenant_code: Mapped[str | None] = mapped_column(String(80), index=True)
    uploaded_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    file: Mapped[dict] = mapped_column(JSONB, default=dict)
    type: Mapped[str] = mapped_column(String(80), nullable=False)
    column_mapping: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(80), default="pending", index=True)
    stats: Mapped[dict] = mapped_column(JSONB, default=dict)
    errors: Mapped[list] = mapped_column(JSONB, default=list)
    valid_preview: Mapped[list] = mapped_column(JSONB, default=list)
    error_preview: Mapped[list] = mapped_column(JSONB, default=list)
    saved_at: Mapped[datetime | None] = mapped_column(DateTime)
