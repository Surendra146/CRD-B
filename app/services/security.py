from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.database.connection import get_db
from app.models import Organization, User

bearer = HTTPBearer(auto_error=False)
MAX_BCRYPT_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")
    if not password_bytes or len(password_bytes) > MAX_BCRYPT_PASSWORD_BYTES:
        raise HTTPException(400, "Password must contain between 1 and 72 UTF-8 bytes")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if hashed_password.startswith("$2a$") or hashed_password.startswith("$2b$") or hashed_password.startswith("$2y$"):
        password_bytes = plain_password.encode("utf-8")
        if len(password_bytes) > MAX_BCRYPT_PASSWORD_BYTES:
            return False
        return bcrypt.checkpw(password_bytes, hashed_password.encode("utf-8"))
    return plain_password == hashed_password


def create_token(payload: dict[str, Any]) -> str:
    settings = get_settings()
    data = payload.copy()
    data["iat"] = datetime.now(UTC).timestamp()
    data["exp"] = datetime.now(UTC) + timedelta(minutes=settings.jwt_expires_minutes)
    return jwt.encode(data, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any] | None:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm], options={"require": ["exp"]})
    except jwt.PyJWTError:
        return None


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials if credentials else request.cookies.get("token")
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authorized to access this route")
    if not credentials and request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        if origin not in get_settings().cors_origins:
            raise HTTPException(403, "Cookie-authenticated changes require an allowed Origin")

    decoded = decode_token(token)
    if not decoded:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

    user_id = decoded.get("userId") or decoded.get("id")
    try:
        user = db.get(User, int(user_id)) if user_id else None
    except (TypeError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token subject") from None
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    if user.password_changed_at:
        changed = user.password_changed_at.replace(tzinfo=UTC).timestamp()
        if not decoded.get("iat") or decoded["iat"] <= changed:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in again after changing your password")

    token_tenant_id = decoded.get("tenantId") or decoded.get("tenant_id")
    if token_tenant_id and user.tenant_id and int(token_tenant_id) != user.tenant_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token tenant does not match user")

    organization = db.get(Organization, user.organization_id) if user.organization_id else None
    if organization and user.tenant_id and organization.tenant_id and user.tenant_id != organization.tenant_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant isolation check failed for this organization")

    request.state.user = user
    request.state.organization = organization
    request.state.organization_id = organization.id if organization else None
    request.state.tenant_id = tenant_id_for_user(user)
    request.state.tenant_code = (organization.tenant_code if organization else None) or user.tenant_code
    return user


def tenant_id_for_user(user: User) -> int:
    tenant_id = user.tenant_id or (user.organization.tenant_id if user.organization else None)
    if not tenant_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tenant associated with this user")
    return tenant_id


def organization_id_for_user(user: User) -> int:
    if not user.organization_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No organization associated with this user")
    return user.organization_id


def require_organization(request: Request, user: User = Depends(get_current_user)) -> User:
    if not request.state.organization:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No organization associated with this user")
    if not request.state.tenant_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tenant associated with this user")
    if user.tenant_id and request.state.organization.tenant_id and user.tenant_id != request.state.organization.tenant_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant isolation check failed for this organization")
    return user


def authorize(user: User = Depends(get_current_user)) -> User:
    return user


def require_owner(user: User = Depends(require_organization)) -> User:
    if user.role != "owner" or not user.organization or user.organization.owner_id != user.id:
        raise HTTPException(403, "Only the organization owner can manage accounts and permissions")
    return user


def require_whatsapp_access(user: User = Depends(require_organization)) -> User:
    if user.role != "owner" and "whatsapp" not in (user.allowed_modules or []):
        raise HTTPException(403, "WhatsApp permission is required")
    return user


def require_module(*modules):
    def dependency(user: User = Depends(require_organization)):
        if user.role != "owner" and not set(modules).intersection(user.allowed_modules or []):
            raise HTTPException(403, "You do not have permission to access this module")
        return user
    return dependency


T = TypeVar("T")


def ensure_tenant_access(record: T | None, user: User, resource_name: str = "Resource") -> T:
    if record is None:
        raise HTTPException(404, f"{resource_name} not found")

    tenant_id = getattr(record, "tenant_id", None)
    if tenant_id is not None and tenant_id != tenant_id_for_user(user):
        raise HTTPException(404, f"{resource_name} not found")

    organization_id = getattr(record, "organization_id", None)
    if organization_id is not None and organization_id != user.organization_id:
        raise HTTPException(404, f"{resource_name} not found")

    return record
