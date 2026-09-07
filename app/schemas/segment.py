from typing import Any

from pydantic import Field

from .common import PayloadSchema


class SegmentRequest(PayloadSchema):
    code: str | None = None
    name: str | None = None
    description: str | None = None
    filters: dict[str, Any] | None = None
    is_active: bool | None = Field(default=None, alias="isActive")


class SegmentCreateRequest(SegmentRequest):
    name: str = Field(min_length=1)


class SegmentUpdateRequest(SegmentRequest):
    pass
