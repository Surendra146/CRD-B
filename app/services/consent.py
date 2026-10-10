from datetime import UTC, datetime, timedelta
from fastapi import HTTPException
from sqlalchemy import select, func
from uuid import uuid4
from app.models import WhatsAppTemplate
from sqlalchemy.dialects.postgresql import insert

from app.config.settings import get_settings
from app.models.saas import ContactConsent, ConsentEvent, MessageRecord
from app.services.meta_whatsapp import normalize_phone


def contact(db, tenant_id, organization_id, phone, lock=False):
    statement = select(ContactConsent).where(ContactConsent.tenant_id == tenant_id,
        ContactConsent.organization_id == organization_id, ContactConsent.phone == normalize_phone(phone))
    return db.scalar(statement.with_for_update() if lock else statement)


def set_consent(db, tenant_id, organization_id, phone, opted_in, source, evidence=None, actor_id=None):
    phone = normalize_phone(phone)
    if opted_in and not str(evidence or "").strip():
        raise HTTPException(400, "Opt-in requires recorded evidence of customer authorization")
    now = datetime.now(UTC)
    db.execute(insert(ContactConsent).values(tenant_id=tenant_id, organization_id=organization_id,
        phone=phone, opted_in=opted_in, source=source, evidence=evidence, created_at=now, updated_at=now)
        .on_conflict_do_update(index_elements=["tenant_id", "organization_id", "phone"],
            set_={"opted_in": opted_in, "source": source, "evidence": evidence, "updated_at": now}))
    db.add(ConsentEvent(tenant_id=tenant_id, organization_id=organization_id, phone=phone,
        opted_in=opted_in, source=source, evidence=evidence, actor_id=actor_id, occurred_at=now))


def assert_send_allowed(db, tenant_id, organization_id, phone, template=None, waba_id=None):
    if not get_settings().enforce_whatsapp_consent:
        return
    row = contact(db, tenant_id, organization_id, phone)
    if not row or not row.opted_in:
        raise HTTPException(403, "This recipient has not opted in or has opted out")
    if template:
        language = (template.get("language") or {}).get("code")
        approved = db.scalar(select(WhatsAppTemplate).where(
            WhatsAppTemplate.tenant_id == tenant_id,
            WhatsAppTemplate.organization_id == organization_id,
            WhatsAppTemplate.whatsapp_template_name == template.get("name"),
            WhatsAppTemplate.content["language"].as_string() == language,
            WhatsAppTemplate.targeting["waba_id"].as_string() == waba_id,
            WhatsAppTemplate.stats["meta_status"].as_string() == "APPROVED",
            WhatsAppTemplate.is_active.is_(True),
        )) if waba_id else None
        if not approved:
            raise HTTPException(403, "Synchronize an approved template for the selected WhatsApp account first")
    else:
        inbound = row.last_inbound_at
        if inbound and inbound.tzinfo is None:
            inbound = inbound.replace(tzinfo=UTC)
        if not inbound or inbound <= datetime.now(UTC) - timedelta(hours=24):
            raise HTTPException(403, "Use an approved WhatsApp template outside the customer service window")


def record_message(db, tenant_id, organization_id, sender, phone, result, bulk_job_id=None):
    now = datetime.now(UTC)
    db.execute(insert(MessageRecord).values(id=uuid4().hex,
        tenant_id=tenant_id, organization_id=organization_id, sender_phone_id=sender,
        recipient=normalize_phone(phone), provider_message_id=result.get("message_id"),
        status=result.get("status", "unknown"), status_timestamp=0, bulk_job_id=bulk_job_id,
        created_at=now, updated_at=now).on_conflict_do_nothing(index_elements=["provider_message_id"]))


def process_inbound(db, connection, message):
    phone = normalize_phone(message.get("from"))
    try:
        when = datetime.fromtimestamp(int(message["timestamp"]), UTC)
    except (KeyError, ValueError, TypeError, OverflowError, OSError):
        raise HTTPException(400, "Invalid inbound message timestamp") from None
    if when > datetime.now(UTC) + timedelta(minutes=5):
        raise HTTPException(400, "Inbound message timestamp is in the future")
    now = datetime.now(UTC)
    db.execute(insert(ContactConsent).values(tenant_id=connection.tenant_id, organization_id=connection.organization_id,
        phone=phone, opted_in=False, last_inbound_at=when, created_at=now, updated_at=now)
        .on_conflict_do_update(index_elements=["tenant_id", "organization_id", "phone"],
            set_={"last_inbound_at": func.greatest(ContactConsent.last_inbound_at, when), "updated_at": now}))
    text = ((message.get("text") or {}).get("body") or "").strip().casefold()
    if text in {"stop", "unsubscribe", "opt out", "cancel", "stop messages"}:
        set_consent(db, connection.tenant_id, connection.organization_id, phone, False, "whatsapp_inbound", message.get("id"))
