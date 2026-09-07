from typing import Any

from pydantic import Field

from .common import PayloadSchema


class SuggestMappingsRequest(PayloadSchema):
    columns: list[str] = Field(default_factory=list)
    type: str | None = None


class ColumnMappingItem(PayloadSchema):
    source_column: str | None = Field(default=None, alias="sourceColumn")
    target_field: str | None = Field(default=None, alias="targetField")
    transformation: str | None = None
    default_value: Any | None = Field(default=None, alias="defaultValue")
    derived_from: list[str] | None = Field(default=None, alias="derivedFrom")


class ColumnMappingRequest(PayloadSchema):
    column_mapping: list[ColumnMappingItem] | None = Field(default=None, alias="columnMapping")
    mappings: list[ColumnMappingItem] | None = None
