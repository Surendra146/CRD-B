"""Database-backed scheduling; row claims prevent competing API workers sending twice."""
import logging
from datetime import datetime, timezone
from threading import Event, Thread

from fastapi import HTTPException
from sqlalchemy import select

logger = logging.getLogger(__name__)


def parse_schedule(value):
    if not value:
        return None
    try:
        scheduled = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if scheduled.tzinfo is None:
            raise ValueError("Timezone required")
        scheduled = scheduled.astimezone(timezone.utc).replace(tzinfo=None)
        if scheduled <= datetime.now(timezone.utc).replace(tzinfo=None):
            raise ValueError("Future time required")
    except (ValueError, TypeError, OverflowError):
        raise HTTPException(400, "Scheduled date and time must be in the future and include a timezone") from None
    return scheduled


def dispatch_due_job(session_factory):
    from app.models import WhatsAppBulkJob, User
    from app.services.security import require_whatsapp_access
    from app.services.whatsapp_connections import resolve_credentials
    from app.routers.communications import dispatch_bulk_job

    with session_factory() as db:
        job = db.scalar(select(WhatsAppBulkJob).where(
            WhatsAppBulkJob.status == "scheduled",
            WhatsAppBulkJob.scheduled_at <= datetime.now(timezone.utc).replace(tzinfo=None),
        ).order_by(WhatsAppBulkJob.scheduled_at).with_for_update(skip_locked=True).limit(1))
        if job is None:
            return False
        job.status = "in_progress"
        db.commit()
        try:
            user = db.get(User, job.created_by)
            if not user or user.tenant_id != job.tenant_id or user.organization_id != job.organization_id or not user.is_active:
                raise HTTPException(403, "Campaign creator no longer has access to this organization")
            require_whatsapp_access(user)
            connection = resolve_credentials(db, user, job.audience_payload.get("sender_phone_number_id"))
            if connection.whatsapp_phone_number_id != job.audience_payload.get("sender_phone_number_id"):
                raise HTTPException(409, "The campaign's WhatsApp sender has changed; create a new campaign")
            dispatch_bulk_job(db, job, connection)
        except HTTPException as error:
            db.rollback()
            db.refresh(job, with_for_update=True)
            job.recipients_summary = [{**r, "status": "failed", "error": error.detail} if r.get("status") == "queued" else r for r in job.recipients_summary]
            from app.services.meta_whatsapp import update_stats
            update_stats(job)
            db.commit()
        return True


def start_scheduler(session_factory):
    stop = Event()

    def run():
        while not stop.is_set():
            try:
                if dispatch_due_job(session_factory):
                    continue
            except Exception:
                # Do not log provider credentials or payloads. Claimed jobs are
                # intentionally not retried after an ambiguous dispatch failure.
                logger.error("WhatsApp scheduler encountered a dispatch error")
            stop.wait(5)

    thread = Thread(target=run, name="whatsapp-scheduler", daemon=True)
    thread.start()
    return stop, thread
