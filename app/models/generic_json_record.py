from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.connection import Base

from .common import TimestampMixin


class GenericJsonRecord(Base, TimestampMixin):
    __tablename__ = "generic_json_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    tenant_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    organization_id: Mapped[int | None] = mapped_column(Integer, index=True)
    tenant_code: Mapped[str | None] = mapped_column(String(80), index=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
