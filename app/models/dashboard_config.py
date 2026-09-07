from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.connection import Base

from .common import TimestampMixin


class DashboardConfig(Base, TimestampMixin):
    __tablename__ = "dashboard_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    tenant_code: Mapped[str | None] = mapped_column(String(80), index=True)
    dashboard_id: Mapped[int] = mapped_column(Integer, ForeignKey("dashboards.id"), index=True, nullable=False)
    layout: Mapped[dict] = mapped_column(JSONB, default=dict)
    widgets: Mapped[list] = mapped_column(JSONB, default=list)
    filters: Mapped[list] = mapped_column(JSONB, default=list)
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
