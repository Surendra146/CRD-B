# WhatsApp delivery authorization fix

Revision `f91c320ab012` follows `f91c320ab011`. It permits `delivery_details`
alongside status fields in the existing `webhook.scope` message-record guard.
No RLS policies, signing checks, tenant checks, credentials or grants change.
The frozen replacement preserves every other guard branch. The migration reads
the installed function body and refuses unexpected drift before replacing it.
CREATE OR REPLACE preserves function identity, ownership and ACLs.

The disposable PostgreSQL regression restores the old guard, reproduces SQLSTATE
42501 with "Webhook cannot replace message identity", restores the fixed guard,
then verifies persistence, duplicate/older statuses and protected identity fields.
This proves the code conflict; the original production exception was not captured.

## Production verification and release plan

No production database was inspected or changed for this implementation.
Use the existing authorized operator connection; do not change credentials.
Before approval, collect these read-only results securely:

```sql
SELECT version_num FROM public.alembic_version;
SELECT pg_get_functiondef('hanuram_auth.guard_row()'::regprocedure);
SELECT pg_get_triggerdef(oid), tgenabled FROM pg_trigger
WHERE tgrelid='public.message_records'::regclass AND NOT tgisinternal;
SELECT proowner::regrole, prosecdef, proconfig, proacl
FROM pg_proc WHERE oid='hanuram_auth.guard_row()'::regprocedure;
SELECT column_name, data_type FROM information_schema.columns
WHERE table_schema='public' AND table_name='message_records';
SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class
WHERE oid IN ('public.message_records'::regclass, 'public.whatsapp_bulk_jobs'::regclass);
SELECT current_user, session_user;
```

Confirm the deployed application revision, prior database head 011, active guard
attachment, delivery_details column, restricted runtime/control roles and same
authorization installation. Do not publish connection strings or environment dumps.
If production is behind 011, review its pending migrations separately.

After explicit release approval:

1. Take the normal database backup and retain the current application artifact.
2. Coordinate a maintenance window for web and worker processes. Startup and
   readiness require the database revision to match the deployed code head exactly.
3. From the new artifact, run `python -m alembic upgrade f91c320ab012` manually
   using the existing migration operator configuration. Stop on function drift.
4. Release/restart the matching backend and workers; verify `/ready`, not only
   `/health`. No frontend change is required.
5. Observe an authorized signed delivery callback or a normal provider retry:
   verify HTTP 200, stored status/details, and the onboarding delivery indicator.
   Confirm signature rejection and tenant isolation remain intact. Inspect the new
   sanitized class/SQLSTATE/stack-location log if a callback still fails.

## Rollback

Coordinate downtime and restore the application artifact expecting revision 011
with `python -m alembic downgrade f91c320ab011` from the new artifact, then restart
matching processes. Downgrade restores only the previous guard; it retains delivery
details and business records. It deliberately reintroduces the old webhook update
failure, so prefer a reviewed forward correction when possible. Database/application
revision mismatch causes readiness failures. The downgrade also refuses unexpected
function drift. No downgrade, deployment or production migration is automatic.

Unknown message IDs arriving before the send transaction commits remain an existing
reliability limitation outside this minimal authorization fix. Duplicate status
callbacks preserve delivery state; callback receipt timestamps can advance.
