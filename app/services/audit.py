from datetime import UTC, datetime
from app.models.saas import AuditEvent


def audit(db, user, action, resource_id=None, details=None):
    # Callers pass an allowlisted summary, never raw tokens, provider bodies or PII.
    db.add(AuditEvent(tenant_id=user.tenant_id, organization_id=user.organization_id,
                      actor_id=user.id, action=action, resource_id=str(resource_id) if resource_id is not None else None,
                      details=details or {}, occurred_at=datetime.now(UTC)))
