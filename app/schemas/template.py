from typing import Any

from pydantic import Field, model_validator

from .common import PayloadSchema


class TemplateRequest(PayloadSchema):
    @model_validator(mode="before")
    @classmethod
    def reject_provider_metadata(cls, data):
        if isinstance(data, dict):
            for field, reserved in (("targeting", {"waba_id", "meta_id"}), ("stats", {"meta_status", "synced_at"})):
                value = data.get(field)
                if isinstance(value, dict) and reserved.intersection(value):
                    raise ValueError("Meta template identity and approval are maintained by server synchronization")
        return data

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
