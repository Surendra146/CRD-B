from datetime import datetime, timedelta
from typing import Any

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
    return password


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
    data["exp"] = datetime.utcnow() + timedelta(minutes=settings.jwt_expires_minutes)
    return jwt.encode(data, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any] | None:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
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

    decoded = decode_token(token)
    if not decoded:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

    user_id = decoded.get("userId") or decoded.get("id")
    user = db.get(User, int(user_id)) if user_id else None
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")

    organization = db.get(Organization, user.organization_id) if user.organization_id else None
    request.state.user = user
    request.state.organization = organization
    request.state.organization_id = organization.id if organization else None
    request.state.tenant_id = user.tenant_id or (organization.tenant_id if organization else None) or (organization.id if organization else None)
    request.state.tenant_code = (organization.tenant_code if organization else None) or user.tenant_code
    return user


def require_organization(request: Request, user: User = Depends(get_current_user)) -> User:
    if not request.state.organization:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No organization associated with this user")
    if user.tenant_id and request.state.organization.tenant_id and user.tenant_id != request.state.organization.tenant_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant isolation check failed for this organization")
    return user


def authorize(user: User = Depends(get_current_user)) -> User:
    return user
