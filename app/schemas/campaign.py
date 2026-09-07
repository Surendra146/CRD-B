from typing import Any

from pydantic import Field

from .common import PayloadSchema


class CampaignRequest(PayloadSchema):
    name: str | None = None
    description: str | None = None
    type: str | None = None
    trigger: dict[str, Any] | None = None
    template: int | None = None
    template_id: int | None = Field(default=None, alias="templateId")
    audience: dict[str, Any] | None = None
    schedule: dict[str, Any] | None = None
    status: str | None = None
    stats: dict[str, Any] | None = None


class CampaignCreateRequest(CampaignRequest):
    name: str = Field(min_length=1)
    type: str = Field(min_length=1)


class CampaignUpdateRequest(CampaignRequest):
    pass
