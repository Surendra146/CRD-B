# HanuRam enterprise operations

## Preserve the existing database

The current application database has no recorded Alembic revision. Do not run `upgrade head`, `stamp head`, or `create_all` against it. The existing review found 6,999 customers, 4 uploads and 30,222 upload rows. Keep those records and relationships intact.

1. Make a backup using `scripts/backup_database.py --output <private-storage-path>` with `BACKUP_DATABASE_URL` supplied through the operator environment. This runs read-only `pg_dump`; protect backups as customer data.
2. Restore into a separate staging database with the same PostgreSQL version. Confirm counts, organization ownership and representative customer/upload relationships.
3. Run `scripts/tenant_preflight.py`. Compare every existing table, column, index and foreign key with the historical migrations. Establish the correct baseline only after that comparison; a version stamp is a declaration of schema equivalence, not a repair.
4. Rehearse `e73a2109b001` (frozen schema repair), `f91c320ab002` (SaaS schema, sender limits and composite ownership), then `f91c320ab003` (forced tenant RLS). Repair conflicts explicitly; never infer tenant ownership from unrelated records.
5. Apply reviewed database grants from `scripts/database_roles.sql`. Create distinct login credentials. Runtime uses the restricted role; control-plane authentication, signed callbacks and outbox discovery use the privileged control role. Migration credentials are separate and never used by the web process.
6. Run the automated PostgreSQL tests and tenant access smoke checks against staging before a production maintenance window. Roll back an application release by selecting the previous compatible image. These data migrations are forward-only; database rollback requires a rehearsed restore and reconciliation of writes since backup.

## Environment and local processes

Use `.env.enterprise.example` as an additive reference; retain existing environment entries and never copy secrets to Vite variables. Configure `DATABASE_URL`, `CONTROL_DATABASE_URL`, `REDIS_URL`, JWT and Meta secrets, encryption key, exact CORS origins and explicit PlatformStaff permissions. Preserve the encryption key across deploys and store an encrypted recovery copy separately from backups.

Start API: `uvicorn app.main:app --reload`. Start worker: `celery -A app.tasks.celery_app worker --loglevel=INFO --pool=solo` on Windows (`prefork` on Linux). Start exactly one beat process: `celery -A app.tasks.celery_app beat --loglevel=INFO`. The outbox can recover a failed broker publication. Ambiguous Meta sends are recorded as unknown and require reconciliation; automatically resending them could message the customer twice.

Use `CAMPAIGN_TRANSPORT=celery`, `ENFORCE_SUBSCRIPTION=true`, `ENFORCE_WHATSAPP_CONSENT=true`, `REQUIRE_RLS=true`, `ENABLE_DISTRIBUTED_LIMITS=true`, and `AUTO_CREATE_TABLES=false` for enterprise deployment. Configure `MAX_BROADCAST_RECIPIENTS` after load testing; recipients are preserved without truncating delivery history. Redis must use private connectivity and authentication/TLS where supported.

Bootstrap platform staff using `scripts/bootstrap_platform_staff.py --email <existing-user> --permissions tenants.read,...` to inspect the intended grant; add `--apply` to persist it. Tenant owners do not receive platform privileges. Review membership periodically.

## Payments and WhatsApp

Create local immutable plan versions in Platform, then assign or renew organization subscriptions through authorized staff. Expiry and future starts are enforced server-side; cancelled/expired subscriptions cannot send or attach numbers. Review `MANUAL_SUBSCRIPTIONS.md` before manually applying revision `f91c320ab005` and granting subscriptions.read/subscriptions.manage. Existing invoice history is preserved.

Subscription invoices are payment records with buyer snapshots. They are not a substitute for a reviewed GST tax-invoice and credit-note workflow. Refund/dispute events and separate messaging-usage collection are not yet implemented; do not enable those workflows without implementing and testing them.

Managed onboarding uses customer authorization and the existing official Embedded Signup flow. Assisted requests expose customer-facing progress, not API tokens. Platform staff can mark a request ready only after a verified tenant connection and provider reference exist. Provider billing eligibility and credit-line sharing must be established under the confirmed agreement; the generic code cannot perform a BSP-specific credit allocation without its API contract.

Sync templates per WABA before messaging. Sending checks tenant ownership, the selected WABA, Meta approval, opt-in evidence and the 24-hour service window for free-form messages. Incoming signed STOP messages revoke consent. Imported CRM marketing flags do not count as opt-in evidence. The provider statement import records actual usage separately from subscription invoices and never assumes a messaging price from delivery callbacks.

## Render and monitoring

The updated blueprint defines API, worker, one beat process and private Redis. Populate secrets manually in the `hanuram-enterprise` environment group before deployment; Render does not accept `sync: false` in groups. Review and replace conflicting per-service variables, especially the old database owner URL. See https://render.com/docs/blueprint-spec for the supported configuration. `DATABASE_URL` and `CONTROL_DATABASE_URL` must point to the EXISTING database with distinct roles. Do not create a replacement production database. Deploy only after the baseline and RLS migration rehearsal. Run migrations as a release operation with migration credentials; web startup does not repair a database.

`/health` is liveness; `/ready` verifies database and Redis connectivity. Monitor readiness failures, webhook rejection/error rates, pending outbox age, unknown deliveries, campaign failures, database connections, Redis memory and eviction, invoice mismatches and halted subscriptions. Configure Render log retention and alerts in the provider dashboard. Keep access tokens, authorization headers, raw webhook bodies and contact data out of logs.

Use managed PostgreSQL point-in-time recovery on an eligible paid plan, daily encrypted logical backups in separate storage, documented retention and at least quarterly restore drills. Define measurable RPO/RTO with the business and verify recovery against those targets. A validated archive catalog alone does not prove restorability.

CI includes backend unit/API tests, frozen migration execution and forced-RLS tests using a restricted PostgreSQL role, plus frontend build/tests/lint. Actual Render deployment, a real Redis worker smoke test, Meta/BSP billing setup have not been performed from this workspace.
