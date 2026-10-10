> Current subscription workflow: manual PlatformStaff assignment, renewal and cancellation. Online payment integration has been removed; provider checkout references below describe earlier checkpoints and are superseded. See the backend MANUAL_SUBSCRIPTIONS.md.

# Enterprise SaaS implementation status

9 October 2026. The architecture review is in the frontend repository at
`docs/ENTERPRISE_SAAS_REVIEW.md`. This is an incremental implementation, not a
production-ready completion of the full enterprise roadmap.

Phase A: enterprise role defaults, owner/admin account management, viewer write
denial, strict JWT tenant validation and suspension enforcement, collision-safe
business registration, null ownership denial, and tenant-owned campaign template
references. Existing custom/member grants remain supported. Startup no longer
rewrites owner grants. Role responses match the existing frontend profile UI;
member edits now persist role/email/password changes and password changes revoke
older JWTs. The frontend denies unassigned modules and resets cache on identity
changes. Existing Embedded Signup, encryption and signed delivery webhooks remain.

Schema preparation: frozen Alembic revision `e73a2109b001` repairs tenant columns
missing from the initial chain and adds four existing marketing tables. It only
fills missing tenant IDs from established organization ownership, rejects conflicts
and upload-parent mismatches, and preserves customer IDs/rows. It is forward-only
to avoid destructive rollback. Generic records without an organization remain
nullable pending a dedicated control-plane/tenant-data classification.

No migration has been applied to the application database. Do not change
AUTO_CREATE_TABLES or automatically deploy this revision until the deployed
schema/history and backup restore have been reviewed. This revision requires an
online database connection for inspection/backfill and does not support --sql.
It is NOT an RLS implementation; strict database-level isolation remains pending.

Run read-only inventory from the backend working directory:

```powershell
.venv/Scripts/python.exe scripts/tenant_preflight.py
```

Run regression and rolled-back migration tests using a dedicated *_test database:

```powershell
.venv/Scripts/python.exe scripts/run_enterprise_tests.py
```

Migration tests use temporary schemas and roll back DDL. Before a real migration,
restore a backup to a separate database, review preflight results and Alembic
history, run `alembic upgrade head` there, and compare row counts and tenant IDs.
Do not blindly stamp a database whose tables were created by create_all.

Remaining phases: full PostgreSQL RLS/context and composite foreign keys; business
profiles/platform staff and audit; Razorpay test-mode subscription/renewal/invoice
integration; managed multi-number onboarding and template sync; consent/window
enforcement and Celery/outbox/message usage ledger; production monitoring, shared
limits, backup drills, and scalable Render deployment. Existing direct/bulk sends
still need compliance enforcement before enterprise launch.

User confirmed an approved centralized Meta/BSP billing arrangement and selected
Razorpay test mode first. Actual provider identity, API contract, readiness and
usage-feed configuration remain unverified. No prices, external payments,
WhatsApp sends, deployments or live database writes were introduced.

Read-only application preflight found 6,999 customers, four uploads, and 30,222
upload rows, with no null/conflicting ownership in the inspected tables. The
inspected tenant columns and marketing tables already exist, but no Alembic
revision is recorded. Reconcile the full existing schema and migration history
on an isolated restored copy before establishing a baseline; do not run upgrade
head against this database or blindly stamp a revision. No application data was
changed. Frontend RBAC tests, build and lint passed.
