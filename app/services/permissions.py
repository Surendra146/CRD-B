from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User

DEFAULT_ALLOWED_MODULES = [
    "custom-dashboards",
    "import",
    "campaigns",
    "customers",
    "communications",
    "notifications",
    "templates",
    "segments",
    "webhooks",
    "reports",
    "dashboards",
    "excel",
    "analytics",
    "uploads",
    "roles",
    "users",
    "settings",
    "whatsapp",
    "system",
]


def resolve_allowed_modules(role: str, allowed_modules: list[str] | None = None) -> list[str]:
    if role == "owner":
        return list(allowed_modules or DEFAULT_ALLOWED_MODULES)
    return list(allowed_modules or [])


def backfill_owner_modules(db: Session) -> int:
    owners = db.scalars(select(User).where(User.role == "owner")).all()
    updated_count = 0
    for owner in owners:
        if owner.allowed_modules != DEFAULT_ALLOWED_MODULES:
            owner.allowed_modules = list(DEFAULT_ALLOWED_MODULES)
            updated_count += 1
    if updated_count:
        db.commit()
    return updated_count
