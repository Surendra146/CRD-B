# Render authorization deployment

For the context-lock correction, first complete the installation prerequisites
below, then follow [CONTEXT_LOCK_CONTENTION_FIX.md](CONTEXT_LOCK_CONTENTION_FIX.md)
to apply revision `f91c320ab008` before starting the updated application. The
`f91c320ab007` commands below describe the original baseline installation; the
updated startup check requires `f91c320ab008`. Retention is now separate operator
maintenance, rather than part of authorization requests.

The implementation uses separate `hanuram_runtime` and `hanuram_control` LOGIN
roles, plus three NOLOGIN function owners. All are NOSUPERUSER and NOBYPASSRLS.
Application tables retain ENABLE and FORCE ROW LEVEL SECURITY. This procedure has
been tested in a disposable PostgreSQL cluster, using a non-superuser migration
operator. It has not been executed against Render or an existing local database.

## Authorization boundary

Database credentials alone cannot select an identity, enumerate tenants, or run
jobs. Backend code signs short-lived, purpose-specific assertions with three
independent keys. PostgreSQL checks the installation UUID, login, backend PID,
transaction ID, expiry, authenticated subject, current account state, and current
PlatformStaff permissions. Caller-set tenant GUCs are not an authorization source.
The backend remains trusted to verify passwords/JWTs and Meta signatures before
issuing assertions. Protect these keys as carefully as the JWT signing key.

SECURITY DEFINER functions do not bypass FORCE RLS: their NOLOGIN owners have
explicit, purpose-specific policies and grants. Function owners never own
application tables. Fixed search paths, qualified object references, revoked
PUBLIC EXECUTE, and restricted schema access prevent search-path substitution.
Control-role grants are bounded by purpose, command and target, rather than an
unrestricted control-role policy. Staff mutations require an audit in the same
transaction; subscription snapshots are checked by deferred database triggers.

## Manual installation sequence

1. Keep backend/worker processes stopped during installation. Confirm the chosen
   Render database is the intended empty database. Do not reset a database or
   stamp an unknown legacy schema. Back up any database that has acquired data.
   Run the read-only preflight again if credentials or schema state have changed.

2. Ensure `hanuram_runtime` and `hanuram_control` are separate restricted LOGIN
   users, without any group memberships, CREATE privileges or object ownership.
   The separate offline operator needs CREATEROLE, database/schema CREATE and
   ownership of application objects. Never use its URL as an application URL.

3. Review and run the complete SQL in
   [scripts/render_authorization_operator.sql](scripts/render_authorization_operator.sql)
   using pgAdmin connected as the operator to the intended database. It runs
   only when `current_database()` is exactly `hanuram_production` and the server
   is PostgreSQL 18. Application logins must already have no memberships,
   elevated role attributes, object ownership, or database/schema CREATE access;
   unsafe starting state is rejected rather than silently repaired. Existing
   function owners must be NOINHERIT, have no outbound memberships, and have no
   explicit members other than this directly connected operator. The crypto
   schema must be operator-owned with no other CREATE grantees. It installs
   trusted `pgcrypto` in `hanuram_crypto`, creates the three restricted NOLOGIN
   owners, and prepares temporary operator SET/INHERIT memberships. It contains
   no passwords and does not create application records. If an existing owner
   cannot be assumed, stop and ask its role administrator; do not grant bypass
   privileges or disable RLS. Existing pgcrypto in another schema requires a
   separately reviewed relocation. PostgreSQL 18's `createrole_self_grant` lets
   role creation supply SET/INHERIT authority without granting ADMIN back to the
   role's own grantor.

4. In a private PowerShell process, load the **external operator URL** into process
   variables without typing credentials into command history:

   ```powershell
   $operatorCredential = Read-Host 'Operator database URL' -AsSecureString
   $env:OPERATOR_DATABASE_URL = [System.Net.NetworkCredential]::new('', $operatorCredential).Password
   $env:MIGRATION_DATABASE_URL = $env:OPERATOR_DATABASE_URL
   $env:REQUIRE_RLS = 'true'
   $env:AUTO_CREATE_TABLES = 'false'
   .\.venv\Scripts\python.exe -m alembic upgrade f91c320ab007
   ```

   Run from the backend directory with dependencies installed. This explicitly
   applies the full chain on the empty database, including unchanged historical
   migrations, `f91c320ab005`, then the new `006` and `007` revisions. Historical
   migration files must not be edited. New revisions are forward-only: rollback
   requires a reviewed backup/security procedure. Package the files under
   `alembic/authorization/` together with the revision files.

5. Generate three distinct random keys of at least 32 characters in your secret
   manager. Keep them stable across the backend and its workers. Run:

   ```powershell
   .\.venv\Scripts\python.exe scripts/provision_database_authorization_keys.py --apply
   ```

   Supply the keys at the hidden prompts. They are stored in private
   `hanuram_auth.signing_keys` only by a direct `hanuram_production_user`
   connection to `hanuram_production` with SET authority for
   `hanuram_identity_owner`. Provisioning verifies the owner-controlled tables
   and a single installation UUID. It rejects any existing keys (including a
   partial set), serializes concurrent attempts, and inserts all three in one
   transaction. Rotation requires a separate reviewed procedure; this command
   cannot replace keys. The keys are stored in private
   `hanuram_auth.signing_keys`, inaccessible to application logins. Neither SQL
   migrations nor source files contain keys. This operation intentionally changes
   the selected database and must be run manually. A key change must be coordinated
   with every service; startup verifies key matching and fails closed.

6. Manually configure the backend Render service, and worker/beat services if used:

   | Variable | Value/source |
   |---|---|
   | `DATABASE_URL` | Internal URL for `hanuram_runtime` |
   | `CONTROL_DATABASE_URL` | Internal URL for `hanuram_control`, same database |
   | `DATABASE_AUTH_IDENTITY_KEY` | Matching private identity key |
   | `DATABASE_AUTH_STAFF_KEY` | Matching private staff key |
   | `DATABASE_AUTH_JOBS_KEY` | Matching private jobs key |
   | `REQUIRE_RLS` | `true` |
   | `AUTO_CREATE_TABLES` | `false` |
   | `ENFORCE_SUBSCRIPTION` | `true` |

   Retain other reviewed application settings, JWT key, WhatsApp encryption key,
   Meta secrets, CORS origins, frontend API URL and broker settings. Do not put
   `OPERATOR_DATABASE_URL` or `MIGRATION_DATABASE_URL` in running application
   services. Migrations are an explicit operator action, not a startup command.

7. Review the SQL checks below, then start the updated backend manually. Startup
   validates expected restricted logins, memberships, ownership, function ACLs,
   FORCE RLS, schema grants, migration revision and matching installation/keys.
   A privilege failure is a blocker: investigate it instead of weakening RLS.
   Deploy the frontend against the correct HTTPS backend URL. No frontend files
   were changed by this authorization implementation.

8. Register the intended staff account through the application, then preview its
   exact permissions using the offline operator process:

   ```powershell
   .\.venv\Scripts\python.exe scripts/bootstrap_platform_staff.py --email staff@example.com --permissions subscriptions.read,subscriptions.manage,plans.manage,tenants.read,audit.read
   ```

   Review the account and permission list, then manually repeat with `--apply`.
   The list replaces existing permissions. Add other permissions only when needed.
   The operator function is executable only by the captured installation operator;
   runtime/control cannot bootstrap staff. Tenant owners/admins are not automatically
   PlatformStaff. Manually assign a valid subscription to test tenant accounts.

9. Test registration, login, cross-tenant denial, staff plan creation and manual
   subscription assignment/renewal/cancellation, uploads, job delivery and Meta
   webhooks. Configure Meta against the HTTPS public backend; no live provider
   calls were made by the local tests. For Celery, run the reviewed worker and beat
   process with the same database/key settings and broker; database scheduling
   uses the same leased delivery path. Do not run both transports unintentionally.

10. Remove the operator URL from this process and review temporary owner-role
    memberships. Revoke installation SET/INHERIT access when your role administrator
    permits it; PostgreSQL's creator/grantor membership rules may require administrator
    help. Retain the separate operator offline, never in application services.
    Future ownership-changing migrations need reviewed temporary installation access.

    ```powershell
    Remove-Item Env:OPERATOR_DATABASE_URL
    Remove-Item Env:MIGRATION_DATABASE_URL
    $operatorCredential = $null
    ```

## Read-only verification SQL

Run these using the operator; inspect output rather than changing any flags.

```sql
SELECT current_database(), current_user;
SELECT version_num FROM public.alembic_version;
SELECT rolname, rolcanlogin, rolsuper, rolbypassrls, rolcreaterole, rolcreatedb
FROM pg_roles WHERE rolname IN ('hanuram_runtime','hanuram_control',
 'hanuram_identity_owner','hanuram_staff_owner','hanuram_jobs_owner');
SELECT member.rolname AS member, parent.rolname AS granted_role
FROM pg_auth_members m JOIN pg_roles member ON member.oid=m.member
JOIN pg_roles parent ON parent.oid=m.roleid
WHERE member.rolname IN ('hanuram_runtime','hanuram_control');
SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity,
 pg_get_userbyid(c.relowner) AS owner
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' AND c.relkind='r' ORDER BY c.relname;
SELECT p.proname,pg_get_userbyid(p.proowner) AS owner,p.prosecdef,p.proconfig,p.proacl
FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
WHERE n.nspname='hanuram_auth' ORDER BY p.proname;
```

The application revision should be `f91c320ab007`, application role memberships
should be empty, and tenant/staff/plan tables should show both RLS flags true.
Logging in directly as either application login without an assertion must return
zero protected rows. Do not query or export the private signing key table.

## Local validation and remaining limits

```powershell
.\.venv\Scripts\python.exe scripts/run_authorization_sandbox.py --legacy-tests
```

This creates and destroys an entirely separate local cluster and fresh databases;
the isolated authorization database is named `hanuram_production` to exercise the
production-name guard unchanged. Loopback and a random database marker protect
the test entry point. Operator tests cover fresh/repeat installation, wrong-name
rejection, unsafe privileges/memberships/ownership, extension relocation, and
repair of the operator's temporary INHERIT option.
it does not consume application connection strings. PostgreSQL binaries must be
installed. On Windows, initialization may require running outside the restricted
Codex sandbox. Bootstrap superuser use is confined to initializing this temporary
cluster: application migrations and security tests use restricted roles. The
legacy regression fixture suite uses its own second disposable database.

Assertions expire after 90 seconds per transaction. Uploads commit in chunks;
campaign leases renew on new authorized transactions and expire after 30 minutes
without activity. Monitor large batches, long transactions, broker outages and
failed job creators. Workers retain advisory locking and existing recipient
deduplication; an external network send is not transactionally exactly-once.
Webhook changes commit independently by matched connection; repeated opt-out
events can add consent history while retaining the opted-out state.

Private audit staging records persist after successful transactions and need a
reviewed operator retention procedure at scale; never delete the durable
`audit_events` history. SQL policy performance has not been benchmarked with
production-sized datasets. A compromised backend signing key remains a security
boundary; the database still validates actual staff membership and target scope.
No Render installation or live WhatsApp/Redis delivery was exercised locally.

References: [PostgreSQL role attributes](https://www.postgresql.org/docs/18/role-attributes.html),
[PostgreSQL client settings](https://www.postgresql.org/docs/18/runtime-config-client.html),
[Render supported extensions](https://render.com/docs/postgresql-extensions).
