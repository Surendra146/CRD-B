"""Tenant-scoped module defaults; existing custom grants remain supported."""
from fastapi import HTTPException

DEFAULT_ALLOWED_MODULES = [
    "dashboard", "custom-dashboards", "import", "campaigns", "customers",
    "communications", "notifications", "templates", "segments", "webhooks",
    "reports", "dashboards", "excel", "analytics", "uploads", "roles",
    "users", "settings", "whatsapp", "system",
]

ROLE_MODULES = {
    "owner": DEFAULT_ALLOWED_MODULES,
    "admin": DEFAULT_ALLOWED_MODULES,
    "marketing_manager": ["dashboard", "customers", "campaigns", "segments", "templates", "whatsapp", "communications", "analytics", "reports", "notifications"],
    "sales_agent": ["dashboard", "customers", "analytics", "reports"],
    "viewer": ["dashboard", "customers", "analytics", "reports", "campaigns", "templates", "segments"],
    "member": [],
    "custom": [],
}


def normalize_role(role):
    return str(role or "").strip().lower().replace("-", "_").replace(" ", "_")


def normalize_module(module):
    return "dashboard" if module in {"dashboards", "custom-dashboards"} else module


def resolve_allowed_modules(role: str, allowed_modules: list[str] | None = None) -> list[str]:
    role = normalize_role(role)
    if role not in ROLE_MODULES:
        raise HTTPException(400, "Select a supported tenant role; platform roles cannot be assigned here")
    if allowed_modules is None:
        return list(ROLE_MODULES[role])
    if not isinstance(allowed_modules, list) or any(module not in DEFAULT_ALLOWED_MODULES for module in allowed_modules):
        raise HTTPException(400, "Unknown module permission")
    return list(dict.fromkeys(allowed_modules))


def effective_modules(user):
    if normalize_role(user.role) in {"owner", "admin"}:
        return {normalize_module(module) for module in DEFAULT_ALLOWED_MODULES}
    return {normalize_module(module) for module in (user.allowed_modules or [])}


def builtin_role_profiles():
    return [{"key": role, "name": role.replace("_", " ").title(), "baseRole": role,
             "modules": list(modules), "builtin": True}
            for role, modules in ROLE_MODULES.items() if role not in {"owner", "member", "custom"}]


def backfill_owner_modules(db):
    # Kept as a compatibility hook. Do not rewrite customer grants on API startup.
    return 0
