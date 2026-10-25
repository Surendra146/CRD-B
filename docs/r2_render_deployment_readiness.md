> Configuration update 2026-10-25: `render.yaml` now declares production
> `hanuram_production_ii23` with separate operator provisioning identity.
> Local development uses `hanuram_dev`. Database-name conflicts below describe
> the original inspection, not the corrected local files. Live Render was not changed.

# R2 development deployment on Render: PASS / BLOCKED report

Update 2026-10-25: a default-off `WHATSAPP_SENDING_ENABLED` interlock is now implemented. The statements below about its absence describe the original review. See [implementation, coverage and Render settings](whatsapp_sending_interlock.md) before using this historical deployment plan. Existing live cutover checks remain outstanding.

Review date: 2026-10-24. **Storage implementation: PASS. Live Render cutover and dispatch restart: BLOCKED pending the checks and approvals below.** This is a repository review, not a production inspection. No production connections, Render configuration changes, migrations, workers, Beat processes, provider messages, pushes or deployments were performed.

User-supplied target: database `hanuram_production_ii23`, PostgreSQL 18.6 with FORCE RLS; private bucket `hanuram-media-prod`; services `cbd-backend`, `hanuram-campaign-worker`, `hanuram-campaign-beat`. These live identities, bucket privacy and successful real R2 operations are user-reported, not independently reverified here. Dummy data and a pre-launch deployment do not prevent configured tenant credentials from sending actual WhatsApp messages.

## 1. Integration and startup review

| Area | Result | Evidence/limit |
|---|---|---|
| Common storage factory | PASS | `app/services/template_media.py` imports `get_media_storage` from `media_storage/factory.py`. Both asset creation and retrieval use it. |
| API media | PASS | `routers/templates.py` uses `store_asset` for upload and `asset` for private preview, with existing template ownership enforcement. |
| Worker media | PASS | `tasks.deliver_job` → `communications.dispatch_bulk_job` → `template_workflow.hydrate_media` → `template_media.sending_media` → `asset` → same factory. No separate worker storage implementation. |
| Approval samples | PASS | `template_workflow.submit` → `sample_handle` → `asset` → factory. Sample handles remain distinct from send-time Meta media IDs. Submitting is an external Meta operation; exclude it from initial storage-only acceptance. |
| Queued snapshots | PASS, code | `audience_payload.template_snapshot` retains template/asset IDs and approved definition; dispatch checks owned template and live Meta approval, then uploads retrieved bytes to Meta. Current production snapshot inventory is unknown. |
| Beat settings | PASS, configuration required | `celery -A app.tasks.celery_app beat` imports `app/tasks.py`, which calls shared `get_settings()` at import. With `MEDIA_STORAGE_BACKEND=r2`, all four R2 fields must be nonempty even on Beat. Beat schedules `hanuram.publish_due` every 10 seconds; publication runs in a worker. |
| Private R2 | PASS, code | HTTPS endpoint validation, Signature V4, bucket-scoped credentials supplied server-side, bounded reads, timeouts, three total attempts and create-only writes. No public access or browser CORS required for this flow. Actual bucket policy/credentials remain deployment checks. |
| Isolation/integrity | PASS, tests | Existing ownership checks, shared safe keys, local containment and SHA-256 integrity preserved. No object keys or credentials added to frontend responses. |
| Transaction failures | PASS, tests | New-object cleanup after confirmed failed flush/constraint rejection; uncertain COMMIT retains object for reconciliation. No R2-to-local fallback. |
| Live compatibility | BLOCKED | `/health` and `/ready` do not test R2. Installed Render release, actual environment, memory capacity and R2 permissions have not been inspected. |

Settings load `.env` without overriding existing process variables and are cached per process. Changes require a controlled restart of every consumer. The default backend is still `local`; explicitly select `r2` on all three services. Do not rely on an omitted setting to select R2. Missing R2 values fail Settings initialization, but HTTPS/bucket connectivity/permissions are checked when the adapter is constructed/used, not by normal API startup. Most Meta settings are not mandatory at Settings startup: successful boot does not prove provider readiness.

API startup with `REQUIRE_RLS=true` verifies restricted runtime and control logins, role/function/schema protections, schema compatibility, matching authorization installation IDs and signing keys. `/ready` checks both database revisions and Redis when transport is Celery. Worker/Beat do not execute the API lifespan's startup verification. They must receive independently verified matching DB/key configuration before any delivery process is resumed.

## 2. Local filesystem dependencies and compatibility gaps

Repository search covered `app` and Python scripts for factory calls, `asset_path`, `.template-media`, configured roots, file reads/writes and deletion. Findings:

| Dependency | What happens with R2 | Required action |
|---|---|---|
| Existing `.template-media` / `WHATSAPP_TEMPLATE_MEDIA_ROOT` objects | Existing metadata does not record storage backend. Switching selects R2 for every asset, including old ones; no legacy lookup occurs. Missing objects break preview, sample submission and send-time media hydration. | Inventory required references through authorized all-tenant access; copy/verify before switch or explicitly accept loss of availability for named dummy assets. No deletion/reset is implied. |
| `template_media.asset_path()` | Remains a local compatibility helper; no production caller found. Existing local corruption test uses it. It must not be used for R2 retrieval. | No code change required for current call sites. External scripts outside this repository remain unverified. |
| `LocalMediaStorage` | Used only when `local` is selected; root must be shared by processes if used. Render instances do not share an ordinary filesystem. | Explicit R2 selection prevents this dependency for new template uploads. Keep existing files for rollback. |
| MP4 validation | Writes upload bytes to a temporary local MP4 and invokes `WHATSAPP_FFPROBE` or `ffprobe`; temporary directory is cleaned afterward. This is processing, not durable storage. | Writable temporary space and an installed ffprobe binary are required on processes performing video validation. Neither inspected Dockerfile nor native Render build installs it. A Windows executable path cannot be reused on Render Linux. |
| Celery Beat scheduler file | Default Celery Beat uses a local schedule database. This is not template media and should not be moved into R2. | Verify writable working directory; run one Beat. Restart can republish periodic tasks, so job safety still depends on DB claims/idempotency. |
| Non-template `media_files` URLs | `meta_whatsapp.build_message` expects a publicly reachable HTTPS URL for free-form image/video/document messages. It does not resolve private R2 keys. | Do not put private R2 URLs/keys into this existing URL-only field or make the bucket public. Supporting private uploaded media there would require separate scoped code changes. |
| CRM CSV/Excel imports and exports | Imports use in-memory parsing and durable DB staging; generated reports are separate from template assets. No additional persistent local template-media read path found. | No R2 rewrite required for these routes. |

`workflow.assets`, current draft header, submitted/approved sample asset IDs, approved history and queued snapshots all matter for old media. The earlier all-tenant audit remains blocked under current runtime/control permissions. Do not interpret RLS-filtered zero rows as no required media. Also do not assume marking a campaign paused makes its assets irrelevant to future resumption.

Reads and Meta multipart construction still buffer bounded whole objects (up to 100 MiB for a document, with extra copies possible). This is not streaming end to end. Render process memory, concurrency and temporary storage need acceptance checks; no capacity measurements were made here.

## 3. Unintended WhatsApp-send paths

There is **no existing global no-send/dry-run switch**. `ENVIRONMENT=development`, dummy data, R2 selection, subscription checks and consent checks are not send inhibitors.

| Trigger | Potential action |
|---|---|
| Worker starts with existing Redis tasks | Can execute previously queued `deliver_job` or `publish_due`, even while Beat is stopped. Worker startup is not a read-only diagnostic. |
| Beat runs | Publishes periodic outbox tasks every 10 seconds; a worker claims due jobs and queues delivery. Existing PostgreSQL outbox can recover work even if Redis appears empty. |
| Due `scheduled` / eligible `in_progress` jobs | Worker may resume queued recipients after scope, creator, sender, eligibility and locking checks. Those checks authorize sending; they do not turn it into a simulation. |
| FastAPI with `CAMPAIGN_TRANSPORT=database` | Lifespan starts the database scheduler thread. Do not switch transport as a way to pause Celery. Unscheduled bulk submission on a non-Celery transport can also dispatch inline. |
| Authenticated direct-send API | `communications.send_whatsapp` sends synchronously regardless of worker/Beat state. Block messaging route access during storage-only testing. |
| Bulk-send API with Celery | Creates due/scheduled jobs and PostgreSQL outbox records. A later consumer restart can send them. Do not create test campaigns on this deployment during the no-send phase. |
| Template submit/refresh and queued verification | Can call live Meta APIs; samples upload media even without sending a message. Exclude these from storage-only acceptance; use mocks offline. |

Existing advisory locks, job leases/status checks and recipient state tracking reduce duplicate delivery. Dispatch persists `unknown` before contacting Meta and does not simply retry ambiguous recipients. They do not provide exactly-once external delivery or a guarantee of no sends. Do not requeue/retry ambiguous results as a connectivity test.

**Current pending/scheduled/in-progress job counts, recipient states, outbox leases and Redis queued/reserved/scheduled tasks are unknown.** No production query or broker inspection was performed. Use existing authorized access or a reviewed reporting facility; no control/runtime bypass or job claiming to obtain counts. Until reconciled, restarting either dispatch service is blocked.

## 4. Dependencies and runtime verification

All three native Render builds run `pip install -r requirements.txt`. `boto3==1.43.118` is present; boto3 is imported by the factory's R2 import even when selecting local, so this dependency must ship with the code on every service. Other dependencies use version ranges; local success does not reproduce a fresh Render install or freeze the full environment.

Executed locally during this review:

```powershell
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe -m compileall -q app/services/media_storage app/services/template_media.py app/tasks.py
.venv\Scripts\python.exe -m pytest tests/test_media_storage_r2.py tests/test_media_storage_integration.py tests/test_template_workflow.py -q --basetemp=.\test-temp-r2-readiness -p no:cacheprovider --tb=short
```

Results: dependency check **No broken requirements found**; compilation passed; **105 tests passed**, one existing Starlette/httpx deprecation warning. Local versions: boto3/botocore 1.43.118, Celery 5.6.3, Redis client 5.3.1, FastAPI 0.140.13, psycopg 3.3.5, SQLAlchemy 2.0.51. Tests use local/mock storage and mock provider calls; no real WhatsApp messages or live R2 calls. Earlier authorization/API sandbox results are recorded in `r2_media_storage.md`; they were not rerun for this review. No package installation, server boot, broker connection or production startup test was performed.

Repository `render.yaml` pins Python 3.13.2 and retains existing service commands below. It still declares database `cm_db`/`cbd_user`, differing from the supplied target. **Do not sync this blueprint to fix environment variables.** Review actual service linkage manually; do not recreate the DB or change ownership. No migrations are required by this R2 integration. Confirm deployed DB revision is `f91c320ab012` with approved read-only checks; do not run `upgrade` or `stamp` in this review.

```text
Web:    uvicorn app.main:app --host 0.0.0.0 --port $PORT
Worker: celery -A app.tasks.celery_app worker --loglevel=INFO --concurrency=2
Beat:   celery -A app.tasks.celery_app beat --loglevel=INFO
```

## 5. Exact service environment matrix (prepare only)

Use `ENVIRONMENT=production` even for this Render development deployment, to retain production startup/security behavior. Secret placeholders mean existing reviewed values supplied privately; they are not literal values. Never use the separate operator login for runtime/control. Both DB URLs must target `hanuram_production_ii23` and the same installation.

| Variable | `cbd-backend` | `hanuram-campaign-worker` | `hanuram-campaign-beat` |
|---|---|---|---|
| `PYTHON_VERSION` | `3.13.2` (blueprint) | same | same |
| `ENVIRONMENT` | `production` | same | same |
| `DATABASE_URL` | approved internal restricted `hanuram_runtime` URL | same | same shared configuration |
| `CONTROL_DATABASE_URL` | approved internal restricted `hanuram_control` URL | same | same |
| `REQUIRE_RLS` | `true` | `true` | `true` |
| `AUTO_CREATE_TABLES` | `false` | `false` | `false` |
| `DATABASE_AUTH_IDENTITY_KEY` | existing matching secret | identical | identical |
| `DATABASE_AUTH_STAFF_KEY` | existing matching secret | identical | identical |
| `DATABASE_AUTH_JOBS_KEY` | existing matching secret | identical | identical |
| `JWT_SECRET` | existing stable secret, 32+ characters | identical: shared Settings requires it | identical: shared Settings requires it |
| `JWT_ALGORITHM` | `HS256` unless previously reviewed otherwise | same | same |
| `JWT_EXPIRES_MINUTES` | `1440` (blueprint) | same | same |
| `REDIS_URL` | existing approved authenticated service URL; provider-required TLS | identical broker | identical broker |
| `CAMPAIGN_TRANSPORT` | `celery` | `celery` | `celery` |
| `MEDIA_STORAGE_BACKEND` | `r2` | `r2` | `r2` |
| `R2_ENDPOINT_URL` | `https://<account-id>.r2.cloudflarestorage.com` | identical | identical |
| `R2_BUCKET_NAME` | `hanuram-media-prod` | identical | identical |
| `R2_ACCESS_KEY_ID` | bucket-limited server secret | identical approved access | same configuration required |
| `R2_SECRET_ACCESS_KEY` | matching server secret | identical | identical |
| `WHATSAPP_PROVIDER` | `meta_cloud` | same | same |
| `WHATSAPP_GRAPH_VERSION` | existing reviewed version (`v23.0` default) | same | same |
| `META_APP_ID` | existing designated application ID | same shared configuration | same shared configuration |
| `META_APP_SECRET` | existing server secret; retain webhook validation | same shared configuration | same shared configuration |
| `WHATSAPP_SIGNUP_CONFIG_ID` | existing designated signup config ID | same shared configuration | same shared configuration |
| `WHATSAPP_VERIFY_TOKEN` | existing webhook secret | same shared configuration | same shared configuration |
| `WHATSAPP_TOKEN_ENCRYPTION_KEY` | existing stable secret matching encrypted DB rows | identical | same shared configuration |
| `ENFORCE_SUBSCRIPTION` | `true` | `true` | `true` |
| `ENFORCE_WHATSAPP_CONSENT` | `true` | `true` | `true` |
| `MAX_BROADCAST_RECIPIENTS` | `1000` (existing blueprint; do not use as safety interlock) | same | same |
| `ENABLE_DISTRIBUTED_LIMITS` | `true` | same shared configuration | same |
| `TENANT_REQUESTS_PER_MINUTE` | `300` default unless existing reviewed override | same | same |
| `ENABLE_REDIS_PROGRESS` | `true` | same | same |
| `ENABLE_SOCKET_PROGRESS` | `false` | same | same |
| `CORS_ORIGINS` | exact approved frontend origin(s) | not functionally needed; same reviewed value acceptable | same |
| `WHATSAPP_FFPROBE` | installed Linux binary path or `ffprobe` on PATH; unset a Windows override | only needed where validation is invoked | not functionally needed |
| `WHATSAPP_TEMPLATE_MEDIA_ROOT` | optional/unused for durable R2 reads | same | same |

R2 account ID is embedded in the endpoint; no separate `R2_ACCOUNT_ID` setting exists. Sender IDs/access tokens are tenant-owned encrypted database connections, not global environment variables. `OPERATOR_DATABASE_URL`, `MIGRATION_DATABASE_URL`, `BACKUP_DATABASE_URL` and `AUTHORIZATION_PREFLIGHT_URL` must stay out of runtime service environments. Do not rotate encryption/signing keys as part of a storage cutover. Shared group changes can restart/start processes: coordinate service pause before applying any approved change.

## 6. Safe development cutover and rollback

No step below is executed by this report. Each service/configuration/cloud/test write requires explicit approval at execution time.

1. **Approve maintenance pause.** Record live resource identities, release commit/revision, environment configuration references and pre-cutover recovery evidence. Pause auto-deploy behavior for this window so changes cannot unexpectedly start dispatch.
2. **Approve dispatch/ingress controls.** Stop Beat, allow active work to drain with bounded observation, then stop consumers. Account for other worker instances/local clients. Restrict direct-send and campaign-creation endpoints during testing; preserve signed webhook verification. Keep `CAMPAIGN_TRANSPORT=celery`, so the API does not start its database scheduler. Stopping dispatch services alone is insufficient for direct API sends. If operational ingress controls cannot enforce this, cutover remains blocked pending a separately implemented/tested send interlock or equivalent isolation.
3. **Resolve existing work and media.** Obtain authorized pending-job/outbox/broker evidence without claiming tasks or consuming queues. Preserve ambiguous send states. Inventory local media plus draft/approved/history/snapshot references and verify required objects exist under identical R2 keys. All-tenant access is unresolved; do not bypass RLS. Dummy assets may instead be explicitly excluded from acceptance with a documented effect on old templates/campaigns, but that does not make missing data disappear or authorize deletion. Retain backups/files/objects.
4. **Approve coordinated configuration/code cutover.** Use existing Render services; prepare the matrix on all three, keep dispatch services stopped, and avoid a rolling mix of local readers and R2 writers. Use the tested integrated code and reviewed dependency build. Do not sync the mismatched DB blueprint, reset data or run migrations. Confirm the paused service state survives configuration changes; otherwise stop before applying them.
5. **Approve controlled storage-only acceptance writes.** On web, with send/campaign routes blocked, upload one valid test image and PDF to a designated authorized template; check returned metadata, authenticated preview, integrity and tenant/org denial. Test video only after ffprobe availability is proven. Keep objects for review; cleanup/deletion needs separate approval. `/ready` alone is insufficient. Do not submit templates to Meta, create campaigns or call direct-send endpoints.
6. **Validate worker compatibility without delivery.** Use existing offline mocked tests for approval/hydration. If actual Render worker credentials must be tested, separately approve a short-lived non-Celery diagnostic that reads an explicitly authorized known object via the factory and emits pass/fail only; it must not call `deliver_job`, `publish_due`, `verify_queued`, `sending_media` or provider APIs. No such diagnostic is executed or supplied here. Do not start a campaign worker as a storage diagnostic.
7. **Keep messaging paused until expressly authorized.** Reconcile queued tasks/outbox and active recipients before any later worker/Beat restart. Any purge/cancellation must be targeted, authorized and auditable; never flush shared Redis or silently rewrite job state. Resume one Beat only after a separately approved messaging test plan or continued no-send enforcement. Restarting consumers with valid sender credentials can send real messages.

Rollback must preserve current DB references and both old/new objects. Before new writes, coordinate reversion of all services to the recorded compatible configuration, with verified original local objects available to each process. Ordinary Render instance files are not durable/shared recovery storage.

After R2 uploads, **do not simply toggle to local or deploy old local-only code**. Retain an R2-compatible prior code version, or first obtain approval to copy all newly referenced objects to their exact legacy keys, verify size/SHA-256 and ensure all consumers share that restored storage. Reconcile metadata committed during cutover and ambiguous commits. A DB restore is a separate destructive operation requiring its own backup/restore plan and fresh approval; it does not roll back R2 or Redis. Keep orphan candidates until a complete authorized inventory proves cleanup is safe. No existing media is automatically deleted.

## 7. Are code changes required?

- **No additional storage integration change is required** for the inspected template upload/preview/approval/queued-worker paths. No schema migration is required.
- **Runtime packaging prerequisite:** video support requires ffprobe provisioning or proof it already exists on Render; current build declarations do not provide it. Choose a reviewed packaging change if absent. Do not claim full media readiness until resolved.
- **Conditional safety change:** there is no global dispatch kill switch. Existing pause plus route/egress isolation can support storage-only testing if independently enforced. If that cannot be guaranteed, a fail-closed, tested send interlock covering both API and worker paths is required before cutover; no unimplemented environment flag is recommended as if it already worked.
- A shared read-only worker startup verification and a secret-safe non-sending storage diagnostic would strengthen operations, but are not part of existing worker boot. They are recommendations, not implemented features.
- General private-R2 support for non-template URL-only `media_files` would require a separately authorized feature change; it is not part of this template-storage cutover.

This task changes only this report. Application logic, settings, deployment files and credentials remain untouched.

## 8. Final gate decisions

| Gate | Decision |
|---|---|
| Repository template-storage integration | **PASS** — shared factory, API/worker paths and security behavior verified by code/tests |
| Local installed dependency consistency/compilation | **PASS** — executed successfully; fresh Render build still unverified |
| Focused storage/template regression | **PASS** — 105 passed, one existing deprecation warning |
| Live DB identity/revision/role protection | **BLOCKED / unverified** — supplied context only; no live checks performed |
| Existing local-media compatibility | **BLOCKED** — complete authorized inventory/copy decision outstanding |
| No unintended provider sends | **BLOCKED** until consumers/producers/direct API paths are demonstrably paused or isolated |
| Video support | **BLOCKED / unverified** until ffprobe and temporary-storage capacity verified |
| Live Render/R2/worker configuration | **BLOCKED / unverified** — user-reported R2 adapter success does not establish current per-service settings |
| Deployment approval | **BLOCKED** — configuration, deployments and controlled acceptance writes require explicit approval |

Next action is human review of this report and an explicit, scoped maintenance/read-only verification plan. Nothing in this report authorizes deployment, environment changes, migrations, queue mutation or WhatsApp delivery.
