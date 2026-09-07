from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.utils.helpers import model_to_dict, slugify
from app.models import Organization, Tenant, User
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MemberCreateRequest,
    MemberRoleUpdateRequest,
    MemberUpdateRequest,
    OrganizationSettingsRequest,
    RegisterRequest,
    ResetPasswordRequest,
    RoleRequest,
    UpdateProfileRequest,
)
from app.services.security import create_token, get_current_user, hash_password, require_organization, verify_password
from app.services.permissions import resolve_allowed_modules



def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    payload = payload.to_payload()
    email = str(payload.get("email", "")).strip().lower()
    password = payload.get("password")
    name = str(payload.get("name", "")).strip()
    company_name = payload.get("companyName") or payload.get("company", {}).get("name") or name
    if not email or not password or not name:
        raise HTTPException(400, "email, password and name are required")
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "User already exists")

    tenant = Tenant(name=company_name, subdomain=slugify(company_name), code=slugify(company_name).replace("-", "")[:20].upper())
    db.add(tenant)
    db.flush()
    user = User(
        email=email,
        password=hash_password(password),
        name=name,
        phone=payload.get("phone"),
        role="owner",
        allowed_modules=resolve_allowed_modules("owner", payload.get("allowedModules")),
        tenant_id=tenant.id,
        tenant_code=tenant.code,
        company={"name": company_name},
    )
    db.add(user)
    db.flush()
    organization = Organization(
        name=company_name,
        slug=slugify(company_name),
        owner_id=user.id,
        tenant_id=tenant.id,
        tenant_code=tenant.code,
        settings={},
        branding={},
        limits={},
        usage={},
    )
    db.add(organization)
    db.flush()
    user.organization_id = organization.id
    db.commit()
    token = create_token({"userId": user.id, "tenantId": tenant.id})
    return {"success": True, "token": token, "data": model_to_dict(user)}


def verify_phone_otp(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.phone_verified = True
    db.commit()
    return {"success": True, "message": "Phone verified"}


def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    payload = payload.to_payload()
    email = str(payload.get("email", "")).strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if not user or not verify_password(str(payload.get("password", "")), user.password):
        raise HTTPException(401, "Invalid credentials")
    user.last_login = datetime.utcnow()
    db.commit()
    token = create_token({"userId": user.id, "tenantId": user.tenant_id})
    response.set_cookie("token", token, httponly=True, samesite="lax")
    return {"success": True, "token": token, "data": model_to_dict(user)}


def logout(response: Response, user: User = Depends(get_current_user)):
    response.delete_cookie("token")
    return {"success": True, "message": "Logged out"}


def get_me(user: User = Depends(get_current_user)):
    return {"success": True, "data": model_to_dict(user)}


def refresh(user: User = Depends(get_current_user)):
    return {"success": True, "token": create_token({"userId": user.id, "tenantId": user.tenant_id})}


def forgot_password(payload: ForgotPasswordRequest):
    return {"success": True, "message": "Password reset request accepted"}


def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    payload = payload.to_payload()
    email = str(payload.get("email", "")).strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if not user:
        raise HTTPException(404, "User not found")
    user.password = hash_password(str(payload.get("password") or payload.get("newPassword") or ""))
    db.commit()
    return {"success": True, "message": "Password reset successful"}


def update_profile(payload: UpdateProfileRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    payload = payload.to_payload()
    for field in ("name", "phone"):
        if field in payload:
            setattr(user, field, payload[field])
    db.commit()
    return {"success": True, "data": model_to_dict(user)}


def change_password(payload: ChangePasswordRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    payload = payload.to_payload()
    if not verify_password(str(payload.get("currentPassword", "")), user.password):
        raise HTTPException(400, "Current password is incorrect")
    user.password = hash_password(str(payload.get("newPassword", "")))
    user.password_changed_at = datetime.utcnow()
    db.commit()
    return {"success": True, "message": "Password changed"}


def get_organization_settings(user: User = Depends(require_organization)):
    if not user.organization:
        raise HTTPException(404, "Organization not found")
    return {"success": True, "data": user.organization.settings or {}}


def update_organization_settings(payload: OrganizationSettingsRequest, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    payload = payload.to_payload()
    if not user.organization:
        raise HTTPException(404, "Organization not found")
    user.organization.settings = {**(user.organization.settings or {}), **payload}
    db.commit()
    return {"success": True, "data": user.organization.settings}


def get_members(user: User = Depends(require_organization), db: Session = Depends(get_db)):
    members = db.scalars(select(User).where(User.organization_id == user.organization_id)).all()
    return {"success": True, "data": [model_to_dict(member) for member in members]}


def create_member(payload: MemberCreateRequest, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    payload = payload.to_payload()
    member = User(
        email=str(payload.get("email", "")).lower(),
        password=hash_password(str(payload.get("password", "password123"))),
        name=payload.get("name") or payload.get("email"),
        phone=payload.get("phone"),
        role=payload.get("role", "member"),
        role_profile_name=payload.get("roleProfileName"),
        allowed_modules=resolve_allowed_modules(payload.get("role", "member"), payload.get("allowedModules")),
        organization_id=user.organization_id,
        tenant_id=user.tenant_id,
        tenant_code=user.tenant_code,
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return {"success": True, "data": model_to_dict(member)}


def update_member(user_id: int, payload: MemberUpdateRequest, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    payload = payload.to_payload()
    member = db.get(User, user_id)
    if not member or member.organization_id != user.organization_id:
        raise HTTPException(404, "Member not found")
    for field in ("name", "phone", "is_active", "allowed_modules"):
        if field in payload:
            setattr(member, field, payload[field])
    db.commit()
    return {"success": True, "data": model_to_dict(member)}


def update_member_role(user_id: int, payload: MemberRoleUpdateRequest, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    payload = payload.to_payload()
    member = db.get(User, user_id)
    if not member or member.organization_id != user.organization_id:
        raise HTTPException(404, "Member not found")
    member.role = payload.get("role", member.role)
    member.role_profile_name = payload.get("roleProfileName", member.role_profile_name)
    member.allowed_modules = resolve_allowed_modules(member.role, payload.get("allowedModules", member.allowed_modules))
    db.commit()
    return {"success": True, "data": model_to_dict(member)}


def get_roles(user: User = Depends(require_organization)):
    if not user.organization:
        raise HTTPException(404, "Organization not found")
    return {"success": True, "data": user.organization.custom_roles or []}


def create_role(payload: RoleRequest, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    payload = payload.to_payload()
    if not user.organization:
        raise HTTPException(404, "Organization not found")
    roles = list(user.organization.custom_roles or [])
    role = {"key": payload.get("key") or slugify(payload.get("name", "role")), **payload}
    roles.append(role)
    user.organization.custom_roles = roles
    db.commit()
    return {"success": True, "data": role}


def update_role(role_key: str, payload: RoleRequest, user: User = Depends(require_organization), db: Session = Depends(get_db)):
    payload = payload.to_payload()
    if not user.organization:
        raise HTTPException(404, "Organization not found")
    roles = list(user.organization.custom_roles or [])
    for role in roles:
        if role.get("key") == role_key:
            role.update(payload)
            user.organization.custom_roles = roles
            db.commit()
            return {"success": True, "data": role}
    raise HTTPException(404, "Role not found")


router = APIRouter()

router.post("/register")(register)
router.post("/verify-phone-otp")(verify_phone_otp)
router.post("/login")(login)
router.post("/logout")(logout)
router.get("/me")(get_me)
router.post("/refresh")(refresh)
router.post("/forgot-password")(forgot_password)
router.post("/reset-password")(reset_password)
router.put("/profile")(update_profile)
router.put("/password")(change_password)
router.get("/organization-settings")(get_organization_settings)
router.patch("/organization-settings")(update_organization_settings)
router.get("/members")(get_members)
router.post("/members")(create_member)
router.patch("/members/{user_id}")(update_member)
router.patch("/members/{user_id}/role")(update_member_role)
router.get("/roles")(get_roles)
router.post("/roles")(create_role)
router.patch("/roles/{role_key}")(update_role)




