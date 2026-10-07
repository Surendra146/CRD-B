from datetime import datetime
from typing import Any

from .common import PayloadSchema
from .communication import CommunicationRequest


class WhatsAppBulkSendRequest(CommunicationRequest):
    title: str = "WhatsApp Campaign"
    audience_type: str = "segment"
    audience: dict[str, Any] = {}
    message: str = ""
    buttons: list[dict[str, Any]] = []
    media_files: list[dict[str, Any]] = []
    batch_delay_seconds: int = 5
    scheduled_at: datetime | str | None = None


class AutoResponderCreateRequest(PayloadSchema):
    name: str
    trigger_type: str = "contains"
    keywords: list[str] = []
    response_message: str
    buttons: list[dict[str, Any]] = []
    media_files: list[dict[str, Any]] = []
    is_active: bool = True
    priority: int = 0


class AutoResponderUpdateRequest(PayloadSchema):
    name: str | None = None
    trigger_type: str | None = None
    keywords: list[str] | None = None
    response_message: str | None = None
    buttons: list[dict[str, Any]] | None = None
    media_files: list[dict[str, Any]] | None = None
    is_active: bool | None = None
    priority: int | None = None


class AutoResponderTestRequest(PayloadSchema):
    message: str
    sender_phone: str | None = None


class GMapsSearchRequest(PayloadSchema):
    query: str
    location: str
    limit: int = 25


class GMapsImportRequest(PayloadSchema):
    leads: list[dict[str, Any]]
    tag: str | None = None


class GroupTaskCreateRequest(PayloadSchema):
    task_type: str
    title: str
    group_name: str | None = None
    raw_text: str | None = None
    group_links: list[str] = []


class NumberFilterRequest(PayloadSchema):
    numbers: list[str] | str
    default_country_code: str = "+91"
