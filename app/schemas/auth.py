from typing import Any

from pydantic import Field

from .common import PayloadSchema


class RegisterRequest(PayloadSchema):
    email: str = Field(min_length=1)
    password: str = Field(min_length=1)
    name: str = Field(min_length=1)
    phone: str | None = None
    company_name: str | None = Field(default=None, alias="companyName")
    company: dict[str, Any] | None = None
    allowed_modules: list[str] | None = Field(default=None, alias="allowedModules")


class LoginRequest(PayloadSchema):
    email: str = Field(min_length=1)
    password: str = Field(min_length=1)


class ForgotPasswordRequest(PayloadSchema):
    email: str | None = None


class ResetPasswordRequest(PayloadSchema):
    email: str = Field(min_length=1)
    password: str | None = None
    new_password: str | None = Field(default=None, alias="newPassword")


class UpdateProfileRequest(PayloadSchema):
    name: str | None = None
    phone: str | None = None


class ChangePasswordRequest(PayloadSchema):
    current_password: str = Field(alias="currentPassword", min_length=1)
    new_password: str = Field(alias="newPassword", min_length=1)


class OrganizationSettingsRequest(PayloadSchema):
    pass


class MemberCreateRequest(PayloadSchema):
    email: str = Field(min_length=1)
    password: str | None = None
    name: str | None = None
    phone: str | None = None
    role: str = "member"
    role_profile_name: str | None = Field(default=None, alias="roleProfileName")
    allowed_modules: list[str] | None = Field(default=None, alias="allowedModules")


class MemberUpdateRequest(PayloadSchema):
    name: str | None = None
    phone: str | None = None
    is_active: bool | None = None
    allowed_modules: list[str] | None = None


class MemberRoleUpdateRequest(PayloadSchema):
    role: str | None = None
    role_profile_name: str | None = Field(default=None, alias="roleProfileName")
    allowed_modules: list[str] | None = Field(default=None, alias="allowedModules")


class RoleRequest(PayloadSchema):
    key: str | None = None
    name: str | None = None
