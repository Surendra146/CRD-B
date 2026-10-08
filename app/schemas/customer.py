from typing import Annotated, Any

from pydantic import Field, StringConstraints

from .common import PayloadSchema


PhoneNumber = Annotated[str, StringConstraints(pattern=r"^[0-9]{10}$", min_length=10, max_length=10)]


class CustomerCreateRequest(PayloadSchema):
    external_id: str = Field(alias="externalId", min_length=1)
    name: str = Field(min_length=1)
    phone: PhoneNumber
    address: str = Field(min_length=1)
    customer_created_date: str = Field(alias="customerCreatedDate", min_length=1)
    email: str | None = None
    whatsapp_number: str | None = Field(default=None, alias="whatsappNumber")
    module_type: str | None = Field(default=None, alias="moduleType")
    demographics: dict[str, Any] | None = None
    lifecycle: dict[str, Any] | None = None
    preferences: dict[str, Any] | None = None
    tags: list[Any] | None = None
    notes: str | None = None


class CustomerUpdateRequest(PayloadSchema):
    external_id: str | None = Field(default=None, alias="externalId")
    name: str | None = None
    email: str | None = None
    phone: PhoneNumber | None = None
    whatsapp_number: str | None = Field(default=None, alias="whatsappNumber")
    address: str | None = None
    customer_created_date: str | None = Field(default=None, alias="customerCreatedDate")
    demographics: dict[str, Any] | None = None
    lifecycle: dict[str, Any] | None = None
    preferences: dict[str, Any] | None = None
    tags: list[Any] | None = None
    notes: str | None = None
    module_tags: list[str] | None = Field(default=None, alias="moduleTags")


class PurchaseRequest(PayloadSchema):
    pass


class InteractionRequest(PayloadSchema):
    pass


class BulkStatusUpdateRequest(PayloadSchema):
    customer_ids: list[int] = Field(alias="customerIds")
    status: str = Field(min_length=1)
