# Render authorization implementation report

Implemented locally. No existing local database, Render database, environment
variable or deployed service was changed. No Git push, deployment or credential
commit was performed. Existing frontend changes and unrelated working-tree files
were preserved. Applied migration files through `f91c320ab005` were not edited.

## Result

Separate runtime/control logins remain NOSUPERUSER/NOBYPASSRLS. Tenant tables retain
FORCE RLS. Three dedicated NOLOGIN owners execute limited identity, staff and job
functions through exact-purpose policies; SECURITY DEFINER is not treated as RLS
bypass. Database assertions bind the actor, target, purpose, installation UUID,
login, backend PID, transaction ID and short expiry. PostgreSQL validates current
account state and current staff permissions. Schema creation, owner memberships,
private keys and operator bootstrap are inaccessible to application logins.

Registration creates an isolated tenant/user/organization atomically. Login reads
only the supplied normalized email before password verification. Account and
member management remain organization-scoped. Background uploads use explicit
authenticated scope; campaign workers use database leases, renewed across their
transactions, and existing advisory locks. Celery claims update the matching
outbox and serialize a lease rather than trusting broker-supplied tenant IDs.
WhatsApp signatures are verified before lookup; lookup returns only the exact
phone/account mapping, without credentials, followed by a scoped runtime session.

Manual subscriptions retain organization locking, payload fingerprints, UUID
idempotency, existing entitlements, future-start/expiry behavior, and audit history.
Deferred triggers reject a subscription commit without a same-transaction audit
matching its target, request, actor, reason and before/after state. Invoice, CRM
and WhatsApp data models are retained.

## New migration revisions

| Revision | Parent | Purpose |
|---|---|---|
| `f91c320ab006` | `f91c320ab005` | Verified authority, private contexts/keys, identity registration, scoped staff/job/webhook functions, explicit grants and FORCE RLS policies |
| `f91c320ab007` | `f91c320ab006` | Ownership/privilege guards, atomic audit checks, offline operator staff provisioning, unique subscription request index |

The revisions require their SQL assets under `alembic/authorization/`. No keys or
passwords are embedded. Both reject automatic downgrade to insecure permissions.

## Changed files

| Area | Files | Change |
|---|---|---|
| Configuration | `.env.example`, `app/config/settings.py` | Blank placeholders/configuration for three independent authorization keys |
| Database sessions | `app/database/authorization.py` (new), `app/database/tenancy.py`, `app/database/connection.py` | Signed transaction authority, scoped workers, startup ownership/grant/key checks, hidden SQL parameters |
| Startup | `app/main.py` | Validate both restricted connections and matching installation; skip unscoped legacy backfill under RLS; preserve existing shutdown fix |
| Identity | `app/services/security.py`, `app/routers/auth.py` | Exact identity lookup, guarded registration/account scope, prevalidated JWT fields; preserve existing dependency signatures |
| Platform | `app/routers/platform.py`, `app/services/manual_subscriptions.py` | Explicit permission/target scope while retaining lifecycle, locks, retries and audits |
| Background work | `app/routers/uploads.py`, `app/tasks.py`, `app/services/whatsapp_scheduler.py` | Explicit upload scopes, leased campaign discovery/delivery, scoped outbox updates |
| Meta | `app/routers/webhooks.py` | Signed exact mapping and separate per-connection runtime transactions |
| Migration entry | `alembic/env.py` | Separate process-only migration credential when RLS is required |
| New revisions | `alembic/versions/f91c320ab006_verified_authorization.py`, `alembic/versions/f91c320ab007_authorization_guards.py` | Reviewed migration installation/grants/guards |
| New SQL assets | `alembic/authorization/f91c320ab006.sql`, `alembic/authorization/f91c320ab007.sql` | Fixed-search-path functions, private state, authorization and audit checks |
| Operator tooling | `scripts/render_authorization_operator.sql` (new), `scripts/database_roles.sql`, `scripts/provision_database_authorization_keys.py` (new), `scripts/bootstrap_platform_staff.py` | Manual non-bypass preparation, hidden key entry, preview-first staff provisioning |
| Preflight | `scripts/render_authorization_preflight.py` (new), `tests/unit/test_render_authorization_preflight.py` (new), `RENDER_AUTHORIZATION_PREFLIGHT.md` (new) | Read-only catalog/privilege checks from the prerequisite phase |
| Validation | `scripts/run_authorization_sandbox.py` (new), `tests/security/test_authorization_roles.py` (new), `scripts/run_enterprise_tests.py` | Dedicated temporary-cluster restricted-role tests, kept separate from legacy fixtures |
| Regression compatibility | `tests/test_enterprise_permissions.py`, `tests/test_security_audit.py` | Update direct helper calls to existing keyword dependency signatures |
| Documentation | `MANUAL_SUBSCRIPTIONS.md`, `RENDER_AUTHORIZATION_DEPLOYMENT.md` (new), this report | Updated operator guidance, exact manual sequence and remaining limits |

## Validation results

Command: `./.venv/Scripts/python.exe scripts/run_authorization_sandbox.py --legacy-tests`.

- **26 real restricted-role security tests passed.** Includes role/FORCE-RLS and
  startup checks; unscoped queries/forged GUCs; private key and SET ROLE denial;
  tenant reads and cross-tenant inserts; ordinary/read-only staff authorization;
  account privilege escalation denial; exact login lookup and atomic duplicate
  registration; member updates/password-token revocation; subscription lifecycle,
  concurrent identical retries/conflicting payloads, audit-required rollback and
  target mismatch; future starts and expiry dashboard counts; upload validation;
  campaign claims, forged scopes/leases and Celery outbox serialization; invalid
  and valid Meta webhook signatures; proof expiry, transaction/PID and installation
  binding.
- **217 regression tests passed, plus 6 subtests.** Includes 18 preflight unit tests.
  Existing Starlette/httpx deprecation warning remains (one warning in regression
  summary; the restricted-role run also emits that dependency warning).
- Full empty-database Alembic chain through `f91c320ab007` installed under a
  NOSUPERUSER/NOBYPASSRLS operator with Render-compatible creation privileges.
- `git diff --check` passed for changed application/migration/script/test files.
- Temporary PostgreSQL cluster was stopped and removed after tests. Existing
  `hanuram_dev`, `hanuram_test` and Render databases were not used.

The sandbox bootstrap superuser only creates the isolated cluster/operator/logins;
it does not perform application migrations or restricted-role tests. Legacy
fixtures run separately in another new database in that temporary cluster.
Historical migration-preservation/RLS suites that mutate their fixture schema are
excluded from the legacy `--no-migrations` run; the new installation is validated
by the dedicated role suite instead.

## Remaining risks and manual steps

No Render privilege blocker was reproduced locally. Provider-side installation
still requires the operator to install trusted pgcrypto and assume the three
NOLOGIN owners. Stop if those permissions differ from the passed preflight.
Signing-key handling remains a trusted backend boundary; production-scale policy
performance, long transactions, actual Redis/Celery delivery and live Meta sends
were not exercised. Job lease recovery, independent webhook commits/retries,
private audit-staging retention and forward-only rollback need operational review.

Follow [RENDER_AUTHORIZATION_DEPLOYMENT.md](RENDER_AUTHORIZATION_DEPLOYMENT.md)
in order: review operator SQL; prepare extension/owners; manually apply migrations;
provision matching keys; manually configure separate restricted service URLs;
validate grants/RLS; start services; register and explicitly grant staff permissions;
assign test subscriptions; run deployment smoke tests; remove operator credentials
from the process and review temporary installation memberships. Do not reset or
stamp the database to bypass installation errors.
