# Manual SaaS subscriptions

Online payment checkout and payment-provider webhook processing have been removed.
CRM, WhatsApp, messaging usage, existing plans, subscriptions and invoice history
remain. Subscription changes do not record a payment or create a paid invoice.

## Operator setup (not performed automatically)

1. Back up the development database and review migration `f91c320ab005` after
   `f91c320ab004`. It drops gateway settings, the provider webhook inbox, plan and
   subscription provider metadata. It renames invoice references in place,
   preserving invoice rows, amounts, buyer snapshots and line items. It does not
   change existing plan assignments, expiry dates, tenant foreign keys or RLS.
   Downgrade is intentionally blocked: dropped metadata requires a backup.
2. Stop the old application before applying the reviewed migration; its checkout
   code requires columns this revision removes. Run `alembic upgrade f91c320ab005`
   manually, then start the updated backend and frontend together. New code cannot
   run correctly against the old invoice schema. Keep `AUTO_CREATE_TABLES=false`;
   automatic table creation is not a replacement for this migration.
3. Keep separate runtime/control credentials and `ENFORCE_SUBSCRIPTION=true`.
   The runtime role should have only SELECT on subscriptions. This migration
   revokes writes from `hanuram_runtime`; review equivalent custom role grants
   manually. Retain the control role's subscription write and audit INSERT access.
4. Grant only the intended active staff account the explicit permissions needed.
   The existing bootstrap script replaces the account's permission list, so
   include existing permissions you intend to retain. Preview first:

   ```powershell
   .\.venv\Scripts\python.exe scripts/bootstrap_platform_staff.py --email staff@example.com --permissions subscriptions.read,subscriptions.manage,plans.manage,tenants.read,audit.read
   ```

   After reviewing, rerun with `--apply` manually. No permissions are granted
   automatically. Tenant owner/admin roles do not confer PlatformStaff access.
5. Remove retired payment-provider secrets from external deployment settings and
   disable the old webhook in the provider dashboard. Removing local code does
   not cancel any real external recurring subscriptions. Review/cancel those
   externally if any were ever created; no provider action was taken here.
6. Review legacy subscriptions with non-active statuses or missing start/end
   dates. They remain unchanged and do not gain access automatically. Assign a
   valid manual period using the staff console when appropriate.

## Subscription behavior

- Plans are local, immutable versions with prices in minor currency units and
  preserved feature entitlements. `total_cycles` remains historical plan data;
  manual subscriptions have no automatic recurring charge or renewal.
- Assignment replaces the current plan/period and clears scheduled cancellation.
  Start and expiry must be timezone-aware; expiry must be later than start and
  now. A future start reports `scheduled` and grants no access before that time.
- Renewal accepts 1–3660 days, extends from the later of current expiry or now,
  and clears scheduled cancellation. Cancelled or unresolved legacy subscriptions
  require explicit assignment to reactivate. Inactive historical plan versions
  may be renewed without changing their entitlements.
- Period-end cancellation preserves access until expiry; immediate cancellation
  revokes access immediately. Expiry is enforced on every access check, so no
  scheduled job is required. Dashboard counts use the same time boundaries.
- Entitlements remain server-owned; WhatsApp number limits still fail closed.
- Operations lock the target organization, validate its tenant, and commit the
  subscription and audit together. Every request requires a UUID `request_id`
  and a reason. Retry identical requests with the same UUID; changed payloads or
  actors using that UUID receive 409. The console retains IDs after failed
  responses while the same form is retried in that mounted session.
- Audit events belong to the staff actor's workspace and include target tenant,
  target organization, reason and before/after snapshots. Platform audit readers
  can inspect cross-tenant operations; tenant readers remain scoped.

## APIs

`GET /api/platform/subscriptions`, `/organizations`, `/subscription-plans`
require `subscriptions.read`. Staff mutations require `subscriptions.manage`:

```
POST /api/platform/tenants/{tenant_id}/organizations/{organization_id}/subscription/assign
POST /api/platform/tenants/{tenant_id}/organizations/{organization_id}/subscription/renew
POST /api/platform/tenants/{tenant_id}/organizations/{organization_id}/subscription/cancel
```

The console needs both read and manage permissions. Plan creation requires
`plans.manage` and now accepts local `amount_minor`, `currency`, `interval`,
`total_cycles` and `whatsapp_numbers`, without a provider plan identifier.
Existing tenant plan/subscription/invoice/usage read APIs remain available.
Payment checkout, reconciliation, tenant cancellation, gateway settings and the
payment webhook routes are removed. The separate Meta WhatsApp webhooks remain.

## Validation

Run API and unit tests without executing migration functions:

```powershell
.\.venv\Scripts\python.exe scripts/run_enterprise_tests.py --no-migrations
```

This requires a dedicated PostgreSQL `*_test` database via `TEST_DATABASE_URL`.
It creates only an isolated temporary test schema and rolls back test data;
it never uses the application database. Migration and forced-RLS suites execute
migration functions and are intentionally excluded. Their new preservation test
is in `tests/integration/test_manual_subscription_migration.py`; run it only after
explicitly choosing to validate migrations in the dedicated test database.

Frontend validation: `npm.cmd run test` (unit tests and Vite build), then
`npm.cmd run lint`. Applied migration files and historical schema dumps retain
their original provider references as historical artifacts.
