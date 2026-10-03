from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column


def utc_database_timestamp() -> datetime:
    """UTC value compatible with existing timestamp-without-timezone columns."""
    return datetime.now(UTC).replace(tzinfo=None)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_database_timestamp, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_database_timestamp, onupdate=utc_database_timestamp, nullable=False)
