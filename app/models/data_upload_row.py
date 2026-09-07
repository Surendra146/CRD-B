from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.connection import Base

from .common import TimestampMixin


class DataUploadRow(Base, TimestampMixin):
    __tablename__ = "data_upload_rows"
    __table_args__ = (
        Index("ix_data_upload_rows_upload_status", "upload_id", "status"),
        Index("ix_data_upload_rows_upload_row", "upload_id", "row_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    upload_id: Mapped[int] = mapped_column(Integer, ForeignKey("data_uploads.id"), index=True, nullable=False)
    organization_id: Mapped[int] = mapped_column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(80), default="staged", index=True)
    raw_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    mapped_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    errors: Mapped[list] = mapped_column(JSONB, default=list)
    warnings: Mapped[list] = mapped_column(JSONB, default=list)
