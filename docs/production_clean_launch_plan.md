> Configuration update 2026-10-25: `render.yaml` now declares production
> `hanuram_production_ii23` with separate operator provisioning identity.
> Local development uses `hanuram_dev`. Database-name conflicts below describe
> the original inspection, not the corrected local files. Live Render was not changed.

# HanuRam Tech production clean-launch plan

Prepared 2026-10-24. **Preparation only. Production is not cleared for reset or launch.** No production connection, backup, restore, migration, configuration update, deployment, worker startup or message delivery was performed in this task. Current business data being described as dummy data does not authorize deletion.

## 1. Repository inspection and blockers

| Inspected component | Finding and consequence |
|---|---|
| Alembic graph | `alembic heads` executed locally: one head, `f91c320ab012`. Chain: `62942c9db687` → `d24bf074d970` → `e73a2109b001` → `f91c320ab002` through `f91c320ab012`. This command reads migration metadata, not production. |
| Initialization | `app/main.py` uses `create_all` only without required RLS. Production must keep `REQUIRE_RLS=true`, `AUTO_CREATE_TABLES=false`. `alembic/env.py` requires a separate `MIGRATION_DATABASE_URL` with RLS enabled. |
| Authorization | Runtime/control and three restricted NOLOGIN function owners; FORCE RLS, signed transaction authority, installation UUID, private signing keys, function ACLs/search paths, ownership and schema grants are checked by startup. Preserve all layers. |
| Operator preparation | `scripts/render_authorization_operator.sql` currently expects `hanuram_production_ii23` and PostgreSQL 18. It creates roles/schema/extension/grants and commits: it is **not preflight**. |
| Initial key provisioning | `scripts/provision_database_authorization_keys.py` currently requires `hanuram_production_ii23` and direct `hanuram_production_user`. It refuses existing/partial keys. Never use it to rotate restored keys. |
| Identity conflict | `render.yaml` declares `cbd-postgres`, database `cm_db`, user `cbd_user`. Older docs mention `hanuram_production`. None proves live identity. Resolve against the actual Render resource and approved connection before any write. Do not rename a database or edit guards to force acceptance. |
| Staff bootstrap | `scripts/bootstrap_platform_staff.py` invokes `hanuram_auth.operator_staff`; it needs an existing active application user and captured installation operator. App owner/admin is not automatically PlatformStaff. Even default preview uses a DB function/transaction: treat as a separately approved operation, not read-only preflight. |
| Render | Web `cbd-backend`, worker `hanuram-campaign-worker`, beat `hanuram-campaign-beat`, Redis `hanuram-redis`; shared `hanuram-enterprise` group. Blueprint uses `checksPass` auto-deployment. Do not sync the blueprint or recreate services. Frontend hosting is outside this blueprint. |
| Readiness | `/health` is process liveness. `/ready` checks runtime/control DB revision and Redis for Celery. API lifespan checks restricted roles, FORCE RLS and matching installation/keys. Neither endpoint proves R2 access, staff provisioning, webhook functionality or worker readiness. Worker/beat do not run the API lifespan checks. |
| Backup helper | `scripts/backup_database.py` falls back to `CONTROL_DATABASE_URL`, uses `--no-owner --no-acl`, and validates only archive listing. **Do not use it as the sole complete clean-launch backup.** Control visibility is not all-tenant backup authorization. |
| Existing docs | `RENDER_AUTHORIZATION_DEPLOYMENT.md` contains historical 007/008 instructions and obsolete database-name claims; `DEPLOYMENT.md` also contains an obsolete statement about webhook POST implementation. Actual code and current migration graph take precedence. |
| Media | Private R2 adapter is integrated. Real R2 upload/download/delete success is user-reported; it was not repeated here. Existing DB-wide media inventory remains blocked by authorization. A DB backup does not contain local files or R2 objects. |

Also inspected `app/config/settings.py`, `app/database/migrations.py`, `app/database/tenancy.py`, `scripts/render_authorization_preflight.py`, deployment guides and R2 storage documentation. Existing application code, environment files and infrastructure configuration are unchanged by this plan.

## 2. Read-only production preflight — approval gate P

Gate P authorizes only named read-only production checks against the independently confirmed Render database/service IDs. It does not authorize backup exports, migrations or configuration changes. No check below was run against production here.

Record privately in a change ticket: Render resource ID, external hostname, database name, operator role, server major version, installation UUID, expected deployed commit and Alembic head. Hosts/identifiers may be recorded privately; never put credentials or connection URLs in tickets or terminal output. Require runtime/control to resolve to the same database and installation. A matching database name alone is insufficient target validation.

Run the existing catalog prerequisite preflight with a hidden operator connection input, from a dedicated PowerShell process. It does not load `.env`. Use approved TLS connection settings, ideally certificate verification; never relax TLS to make it connect.

```powershell
Set-Location 'D:\web apps\Python\CBD_Python'
$preflightSecret = Read-Host 'Approved production operator connection (hidden)' -AsSecureString
try {
    $env:AUTHORIZATION_PREFLIGHT_URL = [System.Net.NetworkCredential]::new('', $preflightSecret).Password
    .\.venv\Scripts\python.exe scripts/render_authorization_preflight.py
    if ($LASTEXITCODE -ne 0) { throw 'Preflight blocked; review the sanitized report' }
} finally {
    Remove-Item Env:AUTHORIZATION_PREFLIGHT_URL -ErrorAction SilentlyContinue
    $preflightSecret.Dispose()
}
```

Use the approved operator's existing PostgreSQL service profile and protected password facility for the supplemental SQL below. A service profile stores connection settings locally; do not print its contents. In an approved SQL client, execute the whole block, inspect privately and roll back. This does not read private signing-key values or business data:

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '10s';
SET LOCAL lock_timeout = '2s';
SELECT current_database(), session_user, current_user,
       current_setting('server_version_num');
SELECT version_num FROM public.alembic_version;
SELECT hanuram_auth.installation_id();
SELECT rolname, rolcanlogin, rolsuper, rolbypassrls, rolcreaterole,
       rolcreatedb, rolinherit
FROM pg_catalog.pg_roles
WHERE rolname IN ('hanuram_runtime','hanuram_control',
  'hanuram_identity_owner','hanuram_staff_owner','hanuram_jobs_owner');
SELECT member.rolname AS member, parent.rolname AS granted_role
FROM pg_catalog.pg_auth_members m
JOIN pg_catalog.pg_roles member ON member.oid=m.member
JOIN pg_catalog.pg_roles parent ON parent.oid=m.roleid
WHERE member.rolname IN ('hanuram_runtime','hanuram_control',
  'hanuram_identity_owner','hanuram_staff_owner','hanuram_jobs_owner');
SELECT n.nspname,c.relname,pg_get_userbyid(c.relowner) AS owner,
       c.relrowsecurity,c.relforcerowsecurity
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname IN ('public','hanuram_auth','hanuram_crypto')
  AND c.relkind IN ('r','p') ORDER BY 1,2;
SELECT extname,extversion,n.nspname AS extension_schema
FROM pg_catalog.pg_extension e
JOIN pg_catalog.pg_namespace n ON n.oid=e.extnamespace;
SELECT p.proname,pg_get_userbyid(p.proowner) AS owner,
       p.prosecdef,p.proconfig,p.proacl
FROM pg_catalog.pg_proc p
JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
WHERE n.nspname='hanuram_auth' ORDER BY p.proname;
SELECT schemaname,tablename,policyname,roles,cmd,qual,with_check
FROM pg_catalog.pg_policies
WHERE schemaname IN ('public','hanuram_auth') ORDER BY 1,2,3;
ROLLBACK;
```

Missing access is a blocker, not permission to change grants. Compare the revision exactly to the release's `alembic heads`; do not stamp it. Check runtime/control have no role memberships, administrative attributes, table ownership or trusted-schema CREATE. Function owners must have the expected restricted attributes and no outbound memberships. Check function signatures, owners, restricted EXECUTE ACLs, fixed search paths, protected schemas and expected policy definitions against the release, not just presence. Existing prerequisite script is necessary but does not certify the final installed design or validate app signing keys.

For independent runtime/control verification, a reviewed operator can run existing `verify_runtime_role` and `verify_authorization_installation` on **Core connections in explicit READ ONLY transactions**, with the production secret set supplied privately. Do not import/start `app.main` or use account/job authorization establishment for this check. Check both installation IDs match and key challenges pass; output only pass/fail. This additional invocation must be prepared/reviewed before use; no new executable wrapper is delivered here.

Service checks, after Gate P: manually inspect Render service identities, deployed commit, start/build commands, environment variable presence (not values), Redis linkage/TLS requirements, one beat instance, bucket privacy and shared R2 configuration. Approved HTTP GET commands:

```powershell
$backendOrigin = Read-Host 'Public HTTPS backend origin (no credentials)'
Invoke-RestMethod -Uri ($backendOrigin.TrimEnd('/') + '/health')
Invoke-RestMethod -Uri ($backendOrigin.TrimEnd('/') + '/ready')
```

These do not start a worker or send messages. Redis PING can be checked by `/ready`; queue inspection must not consume/publish jobs. Additional R2 HEAD/LIST requests require explicit read-only cloud approval and are not part of this preparation. Never claim dependency readiness merely from variable presence.

## 3. Complete backup — approval gate B

Gate B: approve a named database backup export/provider backup, storage destination, access controls, retention and recovery objectives. Use the approved database owner/backup facility only if it can capture **all** schemas and rows under FORCE RLS; database ownership alone does not guarantee that. If it cannot, stop for the provider/backup administrator. Do not grant runtime/control privileges, disable policies, or use partial tenant visibility as a backup.

Preferred: provider-native backup with a documented full-database recovery path. Confirm the actual Render tier supports it: the checked-in blueprint says `free`, but live tier is unknown. Render documents paid-instance PITR and logical exports; Free instances lack those facilities. Verify actual availability rather than assuming coverage. [Render backup documentation](https://render.com/docs/postgresql-backups).

For an approved logical export, use PostgreSQL client tools compatible with the source major version (current operator script requires 18). Configure `PGSERVICE=hanuram_prod_backup` privately with the authorized connection, TLS and protected password file. Do not use a URI on a command line or echo environment variables. Execute only after backup approval:

```powershell
$env:PGSERVICE = 'hanuram_prod_backup'
$backupFolder = Join-Path $env:USERPROFILE ('HanuRamBackups\' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $backupFolder -ErrorAction Stop | Out-Null
$archive = Join-Path $backupFolder 'database.dump'
pg_dump --format=custom --file $archive
if ($LASTEXITCODE -ne 0) { throw 'Backup incomplete; stop' }
pg_restore --list $archive | Out-File (Join-Path $backupFolder 'archive-catalog.txt') -Encoding utf8
if ($LASTEXITCODE -ne 0) { throw 'Archive catalog failed; stop' }
Get-FileHash -Algorithm SHA256 -LiteralPath $archive |
    Select-Object Hash | ConvertTo-Json |
    Set-Content (Join-Path $backupFolder 'archive-sha256.json')
Remove-Item Env:PGSERVICE
```

The unique directory prevents accidental overwrite. Apply reviewed OS access restrictions and encryption before export; archive catalog and checksums are not proof of restoration. Protect archives as production secrets: they include customer data, encrypted provider tokens and private authorization signing material. Keep an encrypted off-machine copy and a secret-manager snapshot with separate access controls.

Do not add schema/table filters, `--no-owner`, `--no-acl`, `--no-policies` or `--enable-row-security`. PostgreSQL normally makes a dump fail if RLS would filter it; its backup session behavior is not a change to table FORCE RLS. If policy/permission prevents a complete authorized dump, **stop**; use the approved provider backup path without weakening RLS. [PostgreSQL pg_dump](https://www.postgresql.org/docs/18/app-pgdump.html).

`pg_dump` does not include cluster roles. If the provider permits it, an authorized backup administrator should also capture a reviewed globals manifest (including memberships/options) separately:

```powershell
# Separate gate B authorization and approved backup service profile required.
pg_dumpall --globals-only --no-role-passwords --file (Join-Path $backupFolder 'globals.sql')
if ($LASTEXITCODE -ne 0) { throw 'Globals inventory incomplete; stop' }
```

Otherwise obtain provider-supported role/ownership/ACL/database-setting inventories and document exact reconstruction. Protect even password-free role manifests. Do not import a shared provider cluster's entire globals dump blindly. Role passwords come from secret management, not printed SQL. [PostgreSQL pg_dumpall](https://www.postgresql.org/docs/18/app-pg-dumpall.html).

Capture database owner/ACLs, schema owners/ACLs, default privileges, role memberships with ADMIN/SET/INHERIT options, database/role settings, extension versions/schema, policies, functions/triggers and Alembic revision. Include private authorization tables in the backup, but never inspect secret contents in terminal output. Separately preserve local media and the existing R2 object namespace/configuration; no media deletion or copying is authorized here. Store the backup timestamp, source resource identity, commit, revision, tool versions and encrypted-secret reference in the backup manifest.

## 4. Isolated restore verification — approval gate V

Gate V approves creation/writes in a named **disposable isolated** PostgreSQL instance, plus secure handling of restored production secrets. Verify it is not production by independent resource ID, loopback/isolated endpoint and a fresh operator-recorded marker. Keep production connection profiles unavailable in this session. Use the source major version and compatible extensions. No web app, worker or beat may connect; block Meta/Redis/R2 egress. A local test cluster may use its local administrator solely to reconstruct roles and ownership; this is not permission to grant elevated production application privileges.

1. Create an empty disposable database and restricted roles from the reviewed role manifest. Preserve original owner names for ownership/ACL fidelity, but assign isolated credentials. Review globals SQL statement by statement; exclude provider-owned roles/tablespaces. Restore extensions into the original schemas. Do not run initial migrations over an already restored schema.
2. Privately set a service profile `hanuram_restore_sandbox` that can only address that isolated instance. Validate identity before the restore. The actual restore command, only after Gate V:

```powershell
$env:PGSERVICE = 'hanuram_restore_sandbox'
psql -X -v ON_ERROR_STOP=1 -c 'SELECT current_database(),session_user,inet_server_addr(),inet_server_port();'
if ($LASTEXITCODE -ne 0) { throw 'Restore target identity check failed' }
# Human confirms the independently recorded disposable endpoint and empty DB.
pg_restore --exit-on-error --single-transaction --dbname 'service=hanuram_restore_sandbox' $archive
if ($LASTEXITCODE -ne 0) { throw 'Restore failed; backup is NOT verified' }
Remove-Item Env:PGSERVICE
```

No `--clean`, privilege stripping, policy removal or trigger disabling. Restoration must preserve ownership and ACLs; errors are blockers, not ignorable warnings. Creating/restoring objects inside the isolated instance is the explicit purpose of Gate V. Validate restricted roles after restore; the isolated restoring administrator is never an application login.

3. Run section 2 catalog checks on the restored database. Compare source/restore table, row and sequence manifests through the authorized backup administrator/facility; tenant-scoped counts do not establish completeness. Check custom schemas, tables, data, sequences, constraints, triggers, indexes, function definitions/owners/ACLs/search paths, policies, schema ownership/default privileges, extensions, installation UUID, expected key count (no values), and original Alembic revision. Source revision may differ from planned release head; record both without stamping either.
4. Validate signing-key challenges with matching restored secrets, runtime/control expected roles and matching installation ID. Exercise unscoped-denial, forged-scope denial and tenant A/B isolation with isolated test identities using reviewed tests only; do not run fixtures that assume a fresh schema against the restored backup. Test decryption only in-memory with sanitized pass/fail output; never display tokens. No provider calls.
5. Separately run the existing `scripts/run_authorization_sandbox.py --legacy-tests` regression suite on its **own generated cluster** after approval. It tests the release security design; it does not verify the restored archive. On Windows use a fresh workspace `PYTEST_ADDOPTS` basetemp to avoid default temporary-directory permission issues. Keep its migrations and bootstrap confined to that generated cluster.
6. Record archive SHA-256, restore command/tool versions, target identity, zero-error restore log, manifest comparisons, restricted-role validation and independent reviewer sign-off. Mark backup verified only after all succeed. Retain isolated data securely; deletion of the disposable instance is another destructive action requiring explicit target-specific approval.

**Current status: no backup created; no isolated restore attempted; no backup verified.**

## 5. What must survive or be explicitly re-established

| Object/configuration | Preservation rule |
|---|---|
| Alembic graph and `alembic_version` | Preserve truthful revision; only actual successful migrations advance it. Package `alembic/authorization/*.sql` with revisions. |
| Authorization schemas | Preserve `hanuram_auth`, `hanuram_crypto`, installation UUID, signing keys, context/lease/staging structures, guard triggers and maintenance functions. Do not classify every non-business table as disposable. |
| Roles/ownership | Preserve runtime/control restrictions, function owners, operator identity/captured grants, schema ownership and ACLs. Database recreation must explicitly reconstruct them under a reviewed plan. |
| FORCE RLS/functions | All policies, restricted definer owners, fixed search paths, revoked PUBLIC execution, grants and constraints must remain or be rebuilt and revalidated before service startup. |
| Secrets | Preserve JWT key, `WHATSAPP_TOKEN_ENCRYPTION_KEY`, all three database authorization keys, Meta app secret/verify token and credentials, R2/Redis secrets in encrypted backup/secret manager. Restoring encrypted rows needs their original encryption key. Coordinated rotation is a separate action. |
| Staff and launch setup | Preserve or explicitly re-create approved active staff identity and PlatformStaff permissions through operator bootstrap; preserve auditability. Inventory subscription plans, manual-subscription settings, system settings and required reference data. Decide which are retained before defining reset scope. |
| Media | Keep old local files and R2 objects. Preserve evidence/references in backup even if dummy DB records are later approved for removal. New numeric IDs can be reused after reset; UUID keys prevent routine collisions but do not replace namespace reconciliation. |
| Redis/outbox | Preserve backup evidence of durable PostgreSQL jobs/outbox and determine stale Redis tasks before consumers restart. Redis is not the authoritative business backup. |
| Render/Meta | Preserve resource identities, domains/CORS, webhook endpoint/signature configuration, connection permissions, deployment commands and exact release artifacts. |

An empty-business-data launch is not synonymous with dropping all schemas. Tenant/account deletion can affect staff FKs, subscription snapshots, audit guards and campaign references. No generic TRUNCATE CASCADE or drop/recreate script is approved by this document.

## 6. Separately gated reset specification — approval gate R

No executable destructive SQL is included. This is intentional: there is no verified complete backup, approved table/row retention manifest or confirmed production identity yet. A concrete reset script can be prepared only after those inputs are available, then requires **fresh human approval immediately before execution**.

Required reset artifact must contain:

1. Exact immutable Render resource ID/hostname, database name, direct operator identity, installation UUID and pre-reset revision captured during preflight. Recheck all live values in the same session before any destructive SQL. SQL asserts database/operator/UUID/revision; host/resource identity is independently checked outside SQL. Any mismatch aborts.
2. An allowlisted table/row reset manifest with FK order, triggers, audited operations, retained configuration/security objects, staff bootstrap and sequence strategy. Inventory by authorized access; do not infer all rows from runtime visibility. Confirm all data classifications with the human owner despite the dummy-data statement.
3. A non-default one-time approval phrase identifying the resource, backup hash and reset-manifest hash; no `--yes`, cached approval or default-to-production target. Print identities only, never secrets. Revalidate after any reconnection. Lock out concurrent deployment/reset actions.
4. A verified backup/restore evidence reference and freeze timestamp. Stop writers, drain/stop dispatch and account for in-flight jobs before reset. Use explicit transaction/timeouts and rollback on error where PostgreSQL permits atomicity. Operations outside a transaction require their own approval and recovery plan.
5. Existing restricted operator access only. FORCE RLS and guard failures stop the run. Do not disable guards, use privileged application logins, invent signing claims or grant blanket access. If current policies do not authorize the selected reset, obtain a separately reviewed administrative design; the plan remains blocked meanwhile.
6. A rollback checkpoint and second-person sign-off. No media deletion, Redis FLUSHALL or database/service recreation bundled into approval. DB recreation is a separate higher-scope decision, not a fallback when data reset fails.

## 7. Prepared Render environment matrix

Prepare values privately; **do not apply them now**. Shared settings must match across web, worker and beat. No operator, backup or migration credentials in service environments. Never copy production secrets into Vite.

| Setting | FastAPI web | Celery worker | Beat |
|---|---|---|---|
| `ENVIRONMENT` | `production` | same | same |
| `DATABASE_URL` | restricted runtime, intended DB | same | same shared configuration |
| `CONTROL_DATABASE_URL` | separate restricted control, same DB | same | same |
| `REQUIRE_RLS` / `AUTO_CREATE_TABLES` | `true` / `false` | same | same |
| `DATABASE_AUTH_IDENTITY_KEY`, `DATABASE_AUTH_STAFF_KEY`, `DATABASE_AUTH_JOBS_KEY` | match installed keys | same | same |
| `JWT_SECRET`, `JWT_ALGORITHM`, `JWT_EXPIRES_MINUTES` | stable secret; `HS256`; `1440` unless existing reviewed settings differ | shared settings | shared settings |
| `WHATSAPP_TOKEN_ENCRYPTION_KEY` | stable existing secret | same | shared settings |
| `WHATSAPP_PROVIDER`, `WHATSAPP_GRAPH_VERSION` | `meta_cloud`, existing reviewed version (`v23.0` default) | same | shared settings |
| `META_APP_ID`, `META_APP_SECRET`, `WHATSAPP_SIGNUP_CONFIG_ID`, `WHATSAPP_VERIFY_TOKEN` | existing production app settings | same required shared configuration | shared settings |
| `MEDIA_STORAGE_BACKEND` | explicit `r2` | same | same; settings import requires configuration |
| `R2_ENDPOINT_URL` | HTTPS account S3 endpoint | identical | identical |
| `R2_BUCKET_NAME`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` | private bucket, bucket-limited object credentials | same bucket/access | same shared settings |
| `REDIS_URL` | intended authenticated Redis; provider TLS settings | identical broker | identical broker |
| `CAMPAIGN_TRANSPORT` | `celery` | same | same |
| `ENFORCE_SUBSCRIPTION`, `ENFORCE_WHATSAPP_CONSENT` | `true`, `true` | same | same |
| `ENABLE_DISTRIBUTED_LIMITS`, `ENABLE_REDIS_PROGRESS`, `ENABLE_SOCKET_PROGRESS` | `true`, `true`, `false` per blueprint | same shared settings | same |
| `MAX_BROADCAST_RECIPIENTS` | existing reviewed limit (`1000` in blueprint) | same | same |
| `CORS_ORIGINS` | exact public frontend origins, no wildcard | not an interactive service | not an interactive service |
| `WHATSAPP_FFPROBE` | working ffprobe executable path or default on PATH | verify availability where validation is used | not media processing |

Tenant WhatsApp sender IDs/tokens are encrypted database connections governed by onboarding; do not replace them with global sender environment variables. Keep the R2 bucket private, without a public development URL/custom domain; current server-to-server flow does not need browser CORS or public object URLs. Web and worker use identical storage configuration. The existing Dockerfile/native Render build does not install ffprobe: verify actual runtime availability before claiming video readiness.

Existing commands for review, not execution:

```text
Web:    uvicorn app.main:app --host 0.0.0.0 --port $PORT
Worker: celery -A app.tasks.celery_app worker --loglevel=INFO --concurrency=2
Beat:   celery -A app.tasks.celery_app beat --loglevel=INFO
```

## 8. Ordered rollout with explicit pauses

1. **Gate P:** approve/read-only-check identities, revision, installed security and dependency configuration. Resolve hardcoded-name conflicts before planning bootstrap. Repository state alone cannot verify the live environment.
2. **Gate B + V:** approve backup and isolated restore. Secure full DB/global/security/media/secret evidence. Do not proceed on archive-list validation alone. Rehearse the exact reset/bootstrap plan on an approved isolated copy.
3. **Gate F — maintenance freeze:** approve service and ingress changes. Pause auto-deploy triggers and uploads/registration/API writes; handle signed webhooks via a reviewed maintenance/retry strategy without disabling signature validation. Stop beat first, drain active tasks with bounded waiting and inspect ambiguous sends, then stop consumers. Include other producers, cron jobs, local schedulers and external API clients. Keep a controlled administrative path only. Record outstanding external callbacks and idempotency implications.
4. Take a final frozen backup and verify the delta/recovery point. Ensure the final artifact is restore-tested, or repeat Gate V for it. Freeze and backup approvals do not authorize reset.
5. **Gate R:** review the exact reset SQL/manifest, target identity and fresh approval phrase against verified backup hash. Execute only that separately approved artifact; stop on any guard error. Nothing destructive is supplied/executed in this preparation.
6. **Gate M — migrations/bootstrap:** on retained schema already at release head, no migration is needed. If behind, approve the exact forward revisions and direct operator session after rehearsal. Only after approval, use process-only `MIGRATION_DATABASE_URL` and `python -m alembic upgrade f91c320ab012` for this inspected release; re-evaluate head if code changes. Never `stamp`, downgrade security revisions or migrate at app startup. Database recreation requires reviewed role/operator preparation, initial migrations and key provisioning before services; do not rerun those blindly on existing/restored data.
7. Establish intended staff identity with approved application registration while public writes remain closed, then approve operator bootstrap preview and exact permissions separately; approve `--apply` only after review. Example command after approval: `python scripts/bootstrap_platform_staff.py --email <approved-email> --permissions tenants.read,subscriptions.read,audit.read`; `--apply` is a separate write gate. Configure plans/manual subscription/onboarding as approved. Do not seed fake connected senders or bypass eligibility checks.
8. **Gate D — configuration/deployment:** apply the reviewed environment matrix and pinned compatible code to web/worker/beat; keep consumers and beat stopped. Confirm no rolling mix of old local-storage readers and R2 writers, no auto migrations and no operator secrets. Validate web startup checks, `/health`, `/ready`, CORS/auth, staff access and tenant A/B isolation through approved acceptance accounts.
9. **Gate Q — stale queue reconciliation:** inspect retained DB outbox/job state and Redis queued/reserved/scheduled tasks. Old tasks can refer to reused job IDs after reset. Do not let them run against new data; prepare and separately approve a scoped queue isolation/purge plan if necessary. Do not flush a shared Redis instance. Preserve evidence of ambiguous sends; restarting a task is not proof that it was never delivered.
10. **Gate T — acceptance writes:** approve controlled image/PDF/video upload/preview and worker storage-access checks with designated test identities. Verify R2 integrity, ownership denial and Meta signatures using mocked events/provider calls. No real WhatsApp delivery is authorized. An application smoke upload and deletion are live changes and need specific approval; do not bundle deletion into testing. User-reported adapter verification does not prove current Render credentials or worker configuration.
11. **Gate L — launch:** fresh approval to start a single beat and intended workers, resume ingress/writes and auto-deployment policy, after all gates and rollback checkpoints pass. This may initiate delivery of eligible jobs: reconcile queues first. Real messaging requires its own explicit authorization. Monitor readiness, queue age, failures, duplicate/ambiguous sends, DB locks, R2 access and webhook retries.

## 9. Rollback procedure

- Keep launch closed while deciding rollback. Stop new producers/beat, drain or quarantine consumers, preserve timestamps, job IDs and ambiguous-send evidence. Do not repeatedly redeliver to test recovery.
- Before any launch writes, use approved full restore/provider recovery into a separately identified target, preserving exact roles/ownership/security keys and revision. Obtain a new approval before restoring over any existing database or changing Render connections. Validate in isolation before cutover. Rehearsal is evidence; a production restore remains a separately approved live operation.
- After launch writes, rollback can lose new tenants/messages/media references. Export and reconcile the post-freeze delta through authorized access before restoring; human owner must approve any explicit recovery-point data loss. Old credentials/signing keys, installation UUID and encryption key must match the restored database. Do not point current services at it until startup security checks pass.
- Restoring older DB state while leaving current Redis tasks active is unsafe. Reconcile tasks/outbox/leases against the restored state before restarting consumers. Provider callbacks can replay events for rows absent in the restore; preserve and reconcile them without disabling webhook verification.
- Record new R2 uploads by cutover time and verified DB references. Retain old and new objects; do not bulk-delete. A database rollback does not roll back R2, and objects with no current reference may still belong to an approved historical version or rollback delta. Use an authorized complete inventory before any later cleanup.
- A simple `MEDIA_STORAGE_BACKEND=local` toggle, or deploying pre-integration code, can strand R2-only uploads. Keep an R2-compatible code version for rollback, or separately approve copying every required object to verified legacy keys with size/hash validation before switching all consumers together. Do not assume an old Render instance retains its filesystem.
- Restore compatible code plus database state as one reviewed change. Forward-only security revisions cannot safely be downgraded. Rotating secrets is a separate coordinated change; retain old encrypted backup access for the agreed retention period.

## 10. Final readiness and approval record

| Item | Current evidence/status |
|---|---|
| Repository migration head | Verified locally: `f91c320ab012`; no production migration performed |
| Initialization, role guards, Render commands, health checks | Inspected in repository; live deployment identity/state unknown |
| R2 integration | Existing code inspected previously; local regression results recorded in `r2_media_storage.md`; real object operation success user-reported, not repeated here |
| Complete production backup | Not created/verified; approved backup facility and all-row visibility unresolved |
| Isolated restore | Not performed; required before reset clearance |
| Production identity/name/version/operator | Unverified; conflicting repository assumptions are a blocker |
| Production revisions/security/keys/services | Read-only procedure prepared; not run |
| Reset scope and administrative authority | No approved manifest or executable reset; blocked pending human review |
| Staff, plans and protected configuration retention | Requires explicit inventory and retention decision |
| Old media and stale broker tasks | All-tenant inventory/queue reconciliation unresolved; no automatic deletion |
| Render config/deployment/acceptance | Matrix and sequence prepared only; no settings or services changed |

Required recorded approvals: **P** production read-only preflight; **B** backup export/facility; **V** isolated restore/rehearsal; **F** freeze/ingress/service changes; **R** exact destructive reset with fresh target-specific approval; **M** exact migrations/bootstrap; **D** config/deployment; **Q** specific stale queue action; **T** controlled acceptance writes; **L** resumption/launch. Any subsequent production restore, media deletion, disposable-instance deletion or live WhatsApp sending needs its own explicit approval. Approval for one gate never implies approval for the next.

**Next safe action:** review and resolve the target identity and backup-access blockers, then explicitly authorize Gate P. No reset, migration or launch is currently authorized by this plan.
