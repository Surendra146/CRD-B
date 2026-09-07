from typing import Any

from pydantic import Field, model_validator

from .common import PayloadSchema


class DashboardCreateRequest(PayloadSchema):
    name: str = Field(min_length=1)
    description: str | None = None
    source_names: list[str] = Field(default_factory=list, alias="sourceNames")
    excel_sources_count: int | None = Field(default=None, alias="excelSourcesCount")
    layout: dict[str, Any] | None = None

    @model_validator(mode="after")
    def source_count_matches(self):
        if self.excel_sources_count is not None and len(self.source_names) != self.excel_sources_count:
            raise ValueError("Source names count must match excelSourcesCount")
        return self


class DashboardUpdateRequest(PayloadSchema):
    name: str | None = None
    description: str | None = None
    layout: dict[str, Any] | None = None
