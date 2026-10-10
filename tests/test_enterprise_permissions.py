from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.services.permissions import resolve_allowed_modules
from app.services.security import ensure_tenant_access, require_module, require_whatsapp_access


def identity(role="viewer", modules=None):
    return SimpleNamespace(role=role, allowed_modules=modules or [], tenant_id=1, organization_id=2)


def request(method):
    return Request({"type": "http", "method": method, "path": "/api/customers/", "headers": []})


@pytest.mark.parametrize("role", ["owner", "admin", "marketing_manager", "sales_agent", "viewer"])
def test_enterprise_roles_have_defaults(role):
    assert "customers" in resolve_allowed_modules(role)


def test_explicit_empty_grants_remain_empty():
    assert resolve_allowed_modules("member", []) == []
    assert resolve_allowed_modules("viewer", []) == []


@pytest.mark.parametrize("role", ["super_admin", "platform_admin", "invented"])
def test_platform_and_unknown_roles_cannot_be_assigned(role):
    with pytest.raises(HTTPException):
        resolve_allowed_modules(role)


def test_empty_member_grants_deny_module_access():
    with pytest.raises(HTTPException):
        require_module("customers")(identity("member"), request("GET"))


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_viewer_cannot_mutate_even_with_assigned_module(method):
    with pytest.raises(HTTPException) as error:
        require_module("customers")(identity(modules=["customers"]), request(method))
    assert error.value.status_code == 403


def test_viewer_can_read_assigned_module():
    viewer = identity(modules=["customers"])
    assert require_module("customers")(viewer, request("GET")) is viewer


def test_viewer_cannot_send_from_background_worker():
    with pytest.raises(HTTPException):
        require_whatsapp_access(identity(modules=["whatsapp"]))


@pytest.mark.parametrize("tenant,organization", [(None, 2), (1, None), (99, 2), (1, 99)])
def test_null_or_foreign_ownership_denied(tenant, organization):
    with pytest.raises(HTTPException) as error:
        ensure_tenant_access(SimpleNamespace(tenant_id=tenant, organization_id=organization), identity(), "Record")
    assert error.value.status_code == 404


def test_dashboard_alias_permission_matches_frontend():
    assert require_module("custom-dashboards")(identity(modules=["dashboard"]), request("GET"))
