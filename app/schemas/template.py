from typing import Any

from pydantic import Field

from .common import PayloadSchema


class TemplateRequest(PayloadSchema):
    name: str | None = None
    category: str | None = None
    whatsapp_template_name: str | None = Field(default=None, alias="whatsappTemplateName")
    content: dict[str, Any] | None = None
    variables: list[Any] | None = None
    targeting: dict[str, Any] | None = None
    stats: dict[str, Any] | None = None
    is_active: bool | None = Field(default=None, alias="isActive")


class TemplateCreateRequest(TemplateRequest):
    name: str = Field(min_length=1)
    category: str = Field(min_length=1)


class TemplateUpdateRequest(TemplateRequest):
    pass
