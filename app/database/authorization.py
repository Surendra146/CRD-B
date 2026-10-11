"""Signed database authority, bound to one backend PID and transaction ID.

Keys are provisioned separately from migrations. Database credentials alone do
not authorize identity discovery, staff operations, or worker scope selection.
"""
import hashlib
import hmac
import json
import time

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.config.settings import get_settings


def enabled():
    return get_settings().require_rls


def apply_authority(connection, authority):
    if not enabled() or connection.dialect.name != "postgresql":
        return
    if not authority:
        return  # No context row for this transaction: RLS denies protected SQL.
    now = time.time()
    deadline = min(now + 90, authority.get("deadline", now + 90))
    if deadline <= now:
        raise HTTPException(401, "Authorization has expired")
    identity = connection.execute(text("SELECT pg_backend_pid(), txid_current()::text, session_user, hanuram_auth.installation_id()")).one()
    claims = {**authority, "pid": identity[0], "xid": identity[1], "login": identity[2],
              "aud": "hanuram-postgres-v1", "exp": deadline, "installation": str(identity[3])}
    key_type = "staff" if claims["purpose"].startswith("staff.") else (
        "jobs" if claims["purpose"].startswith(("job.", "upload.", "webhook.")) else "identity")
    claims["key"] = key_type
    secret = get_settings().database_authorization_keys[key_type]
    if len(secret) < 32:
        raise RuntimeError("Database authorization signing keys must be provisioned before RLS startup")
    payload = json.dumps(claims, sort_keys=True, separators=(",", ":"))
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    try:
        connection.execute(text("SELECT hanuram_auth.establish(:payload, :signature)"),
                           {"payload": payload, "signature": signature})
    except DBAPIError as error:
        if getattr(error.orig, "sqlstate", None) == "42501":
            raise HTTPException(403, "Database authorization denied") from None
        raise


def authorize(db, purpose, **claims):
    if not enabled():
        return
    current = db.info.get("database_authority")
    if current and current.get("sub") and claims.get("sub") not in (None, current["sub"]):
        raise HTTPException(403, "A session cannot change authenticated actor")
    authority = {"purpose": purpose, **claims}
    db.info["database_authority"] = authority
    if db.in_transaction():
        apply_authority(db.connection(), authority)
    else:
        db.connection()  # after_begin installs authority on this transaction.


def actor_claims(user, db=None):
    source = (db.info.get("database_authority") or {}) if db is not None else {}
    return {"sub": user.id, "tenant": user.tenant_id, "org": user.organization_id,
            "iat": source.get("iat", getattr(user, "_authorization_iat", time.time())),
            "deadline": source.get("deadline", getattr(user, "_authorization_deadline", time.time() + 90))}


def account_scope(db, user):
    authorize(db, "account", **actor_claims(user, db))


def staff_scope(db, user, permission, **target):
    authorize(db, "staff." + permission, **actor_claims(user, db), **target)


def upload_scope(db, upload_id, user_id, tenant_id, organization_id):
    authorize(db, "upload.scope", sub=user_id, tenant=tenant_id, org=organization_id, upload=upload_id)


def claim_campaign(db, job_id=None):
    authorize(db, "job.claim", job=job_id, transport=get_settings().campaign_transport)
    row = db.execute(text("SELECT * FROM hanuram_auth.claim_campaign(:job)"), {"job": job_id}).mappings().first()
    db.commit()
    if not row:
        return None
    claim = dict(row)
    claim["lease"] = str(claim["lease"])
    return claim


def campaign_scope(db, claim):
    authorize(db, "job.scope", sub=claim["actor_id"], tenant=claim["tenant_id"],
              org=claim["organization_id"], job=claim["job_id"], lease=str(claim["lease"]))


def lookup_webhook(db, phone, waba):
    authorize(db, "webhook.lookup", phone=phone, waba=waba)
    row = db.execute(text("SELECT * FROM hanuram_auth.webhook_connection()" )).mappings().first()
    return dict(row) if row else None


def webhook_scope(db, connection):
    authorize(db, "webhook.scope", tenant=connection["tenant_id"], org=connection["organization_id"],
              phone=connection["phone_number_id"], waba=connection["waba_id"])
