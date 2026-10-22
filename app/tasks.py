"""Redis/Celery delivery; database outbox recovers missed broker publication."""
from datetime import UTC, datetime, timedelta
from typing import cast

from celery import Celery
from celery.app.task import Task
from fastapi import Request, HTTPException
from sqlalchemy import select
from sqlalchemy.engine import Engine

from app.config.settings import get_settings

settings = get_settings()
celery_app = Celery("hanuram", broker=settings.redis_url)
celery_app.conf.update(task_ignore_result=True, task_serializer="json", accept_content=["json"],
    broker_connection_retry_on_startup=True, worker_prefetch_multiplier=1,
    beat_schedule={"campaign-outbox": {"task": "hanuram.publish_due", "schedule": 10.0}})


@celery_app.task(name="hanuram.publish_due")
def publish_due():
    from app.database.connection import ControlSessionLocal
    from app.models import WhatsAppBulkJob
    from app.models.saas import CampaignOutbox
    with ControlSessionLocal() as db:
        from app.database.authorization import enabled, claim_campaign
        if enabled():
            for _ in range(100):
                claim = claim_campaign(db)
                if not claim:
                    break
                celery_app.send_task(
                    "hanuram.deliver_job",
                    args=[claim['job_id'], claim['tenant_id'], claim['organization_id'], claim],
                )
            return
        rows = db.scalars(select(CampaignOutbox).join(WhatsAppBulkJob, WhatsAppBulkJob.id == CampaignOutbox.bulk_job_id).where(
            WhatsAppBulkJob.status.in_(["scheduled", "in_progress"]), WhatsAppBulkJob.scheduled_at <= datetime.now(UTC).replace(tzinfo=None),
            CampaignOutbox.status.in_(["pending", "published"]),
        ).with_for_update(skip_locked=True).limit(100)).all()
        for row in rows:
            if row.last_attempt_at and row.last_attempt_at > datetime.now(UTC) - timedelta(minutes=2):
                continue
            cast(Task, deliver_job).delay(row.bulk_job_id, row.tenant_id, row.organization_id)
            row.status = "published"
            row.last_attempt_at = datetime.now(UTC)
        db.commit()


@celery_app.task(name="hanuram.deliver_job", acks_late=True, reject_on_worker_lost=True)
def deliver_job(job_id, tenant_id, organization_id, claim=None):
    from app.database.connection import SessionLocal
    from app.models import User, Tenant, WhatsAppBulkJob
    from app.models.saas import CampaignOutbox
    from app.database.tenancy import bind_scope
    from app.services.security import require_whatsapp_access
    from app.services.whatsapp_connections import resolve_marketing_credentials
    from app.routers.communications import dispatch_bulk_job
    from app.database.authorization import enabled, claim_campaign, campaign_scope
    if enabled():
        if claim is None:
            from app.database.connection import ControlSessionLocal
            with ControlSessionLocal() as discovery:
                claim = claim_campaign(discovery, job_id)
        if not claim:
            return
        if (claim['job_id'],claim['tenant_id'],claim['organization_id']) != (job_id,tenant_id,organization_id):
            return
    with SessionLocal() as db:
        if enabled():
            campaign_scope(db, claim)
        bind_scope(db, tenant_id, organization_id)
        job = db.scalar(select(WhatsAppBulkJob).where(WhatsAppBulkJob.id == job_id,
            WhatsAppBulkJob.tenant_id == tenant_id, WhatsAppBulkJob.organization_id == organization_id).with_for_update())
        if not job or job.status not in {"scheduled", "in_progress"}:
            return
        if job.status == "scheduled" and cast(datetime, job.scheduled_at) > datetime.now(UTC).replace(tzinfo=None):
            return
        # Hold a PostgreSQL advisory lock for the entire dispatch, across commits.
        # Use a dedicated connection; returning it to the pool releases it below.
        lock = cast(Engine, db.get_bind()).connect()
        try:
            if not lock.scalar(__import__('sqlalchemy').text("SELECT pg_try_advisory_lock(:key)"), {"key": job_id}):
                return
            user = db.get(User, job.created_by)
            tenant = db.get(Tenant, tenant_id)
            if not user or not user.is_active or not tenant or not tenant.is_active or user.tenant_id != tenant_id or user.organization_id != organization_id:
                job.status = "paused"
                db.commit()
                return
            require_whatsapp_access(request=cast(Request, None), user=user)
            sender = job.audience_payload.get("sender_phone_number_id")
            credentials = resolve_marketing_credentials(db, user)
            if credentials.whatsapp_phone_number_id != sender:
                raise HTTPException(409, "The campaign sender has changed; recreate the campaign")
            job.status = "in_progress"
            db.commit()
            dispatch_bulk_job(db, job, credentials)
            outbox = db.scalar(select(CampaignOutbox).where(CampaignOutbox.bulk_job_id == job_id))
            if outbox:
                outbox.status = "completed"
            db.commit()
        except HTTPException as error:
            db.rollback()
            db.refresh(job, with_for_update=True)
            job.recipients_summary = [
                {**recipient, "status": "failed", "error": error.detail}
                if recipient.get("status") == "queued" else recipient
                for recipient in job.recipients_summary
            ]
            from app.services.meta_whatsapp import update_stats
            update_stats(job)
            db.commit()
        finally:
            lock.execute(__import__('sqlalchemy').text("SELECT pg_advisory_unlock(:key)"), {"key": job_id})
            lock.commit()
            lock.close()
