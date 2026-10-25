# Infrastructure architecture audit

Audit date: 2026-10-24. Status: phase 1 inspected; phase 2 validation blocked. Later implementation phases have not started, following the requested sequential validation gates.

## Existing implementation and reuse

| Area | Actual implementation | Disposition |
|---|---|---|
| API | `app/main.py`, `create_app`, ASGI `app`; `/health`, `/ready` | Reuse entry point, startup checks and readiness |
| Configuration | `app/config/settings.py`, plain `Settings`, cached `get_settings`, `load_dotenv()` | Extend this configuration system, without adding another framework |
| Database | `app/database/connection.py`, SQLAlchemy runtime `SessionLocal` and separate `ControlSessionLocal`, pre-ping pools, hidden SQL parameters | Preserve sessions, role boundaries and URLs |
| Authorization | `app/database/tenancy.py`, `authorization.py`, Alembic authorization migrations | Preserve transaction scope, signed identity/staff/job claims, forced RLS and restricted function owners |
| Startup | `app/main.py` verifies runtime role, both authorization installations and matching installation IDs when `REQUIRE_RLS=true` | Preserve fail-closed checks |
| Operator URLs | `alembic/env.py` consumes `MIGRATION_DATABASE_URL`; `scripts/render_authorization_preflight.py` reads process-only `AUTHORIZATION_PREFLIGHT_URL`; provisioning uses `OPERATOR_DATABASE_URL` | Keep operator credentials out of API, worker and beat environments |
| Redis | `app/redis/connection.py` caches upload progress; `app/middlewares/distributed_limits.py` enforces shared limits; Celery uses the same configured `REDIS_URL` | Reuse Redis; PostgreSQL remains durable source of job state |
| Campaign worker | `app/tasks.py`: Celery `publish_due`, `deliver_job`; beat every 10 seconds; PostgreSQL campaign outbox and authorization claim path | Reuse existing queue, worker and beat |
| Duplicate protection | `deliver_job` uses tenant/org matching, job status checks, PostgreSQL advisory locks, late acknowledgement and worker-loss rejection | Preserve existing semantics; do not claim exactly-once delivery |
| Alternative scheduler | `app/services/whatsapp_scheduler.py`, API lifespan starts it only with `CAMPAIGN_TRANSPORT=database` outside tests | Preserve alternative; use existing Celery transport for requested separate worker |
| Sending | `app/routers/communications.py`, `app/services/meta_whatsapp.py`, `template_workflow.py` | Preserve dispatch, provider payloads, consent, plans, retries and statistics |
| Credentials | `app/services/whatsapp_connections.py`: encrypted tenant/org-owned database connections and sender resolution | Preserve onboarding and encryption; global access-token examples in the request are not the application's credential model |
| Template media | `app/services/template_media.py`, `.template-media` or `WHATSAPP_TEMPLATE_MEDIA_ROOT`; tenant/org/template/UUID file hierarchy | Add storage boundary here after phase 2 passes |
| Media records | Template workflow JSON stores asset ID, type, MIME, size, name and SHA-256 | Preserve IDs, JSON shape, ownership and relationships; no schema change currently indicated |
| Media API | `app/routers/templates.py`: authorized upload and private preview, `template_workflow.owned` | Preserve routes, ownership checks and response contracts |
| Media validation | Pillow images, pypdf PDF checks, ffprobe MP4 codec validation; 5 MB images, 16 MB video, 100 MB documents | Preserve validation before storage and SHA-256 integrity on read |
| ffprobe | `WHATSAPP_FFPROBE` executable override, otherwise `ffprobe`; temporary local MP4 file, bounded subprocess timeout | Preserve temporary processing; no existing FFmpeg transcoding found in inspected media service |
| Meta media | Resumable approval sample upload and separate send-time messaging upload in `template_media.py` | Preserve distinction and fresh worker upload |
| CRM uploads | `app/routers/uploads.py`: CSV/Excel parsing and staged PostgreSQL rows; progress cache and background processing | Do not conflate these imports with template binary storage |
| Webhooks | `app/routers/webhooks.py`: verify token, HMAC SHA-256, constant-time comparison, authorization lookup and scoped delivery processing | Preserve security and idempotency logic |
| Render | Existing `render.yaml`: web, Redis, campaign worker, beat, database declaration | Retain resources; no duplicate worker/queue provisioning |
| Container | Existing multi-stage `Dockerfile`; Python-native Render build | Neither inspected build installs ffprobe; production video validation needs verified executable availability |
| CI | `.github/workflows/backend-ci.yml`: PostgreSQL API tests, coverage, container builds/tests | Preserve workflow and dedicated test DB safeguards |
| Frontend | No `package.json` or React source found in this workspace | Full local React validation needs the frontend checkout |

## Gaps requiring infrastructure changes

1. Local template files are unavailable to a worker on another Render instance. Introduce local and private R2 adapters behind existing asset read/write calls. Keep legacy local root/layout; use server-derived tenant/org/template/asset object keys. Never accept a client storage key or fall back from R2 to local storage.
2. Existing binary operations load bounded complete files into memory. An adapter may provide streaming, but current validation and Meta multipart construction still buffer up to existing size limits. Do not promise end-to-end streaming without a separate behavior review.
3. Existing templates have no storage provenance. Switching a deployment to R2 before copying and verifying all referenced historical objects would break those assets. Inventory, explicit copy, size/hash verification, rollback and a controlled cutover are required; no automatic migration or deletion.
4. Settings currently validate production database presence and JWT strength, but do not enforce local-only development hosts, distinct development Meta credentials, an environment allowlist, explicit production Redis/storage configuration, or mandatory Meta/encryption credentials at process startup. Changes must account for existing tests and optional integrations.
5. `.env.example` currently suggests table auto-creation and does not enable RLS. Secure local examples should follow `LOCAL_DATABASE_SETUP.md`: restricted runtime/control roles, matching local authorization keys, `REQUIRE_RLS=true`, `AUTO_CREATE_TABLES=false`.
6. Redis progress client has no explicit socket timeouts, permanently caches initial connection failure and does not catch later operation failures. Shared rate limiting already uses two-second timeouts and fails closed. Improve only infrastructure failure handling, keeping the durable database state intact.
7. No S3 client or R2 adapter exists in inspected requirements/services. Add a maintained S3 client only when implementing the adapter, with mocked tests and bounded network retries/timeouts.
8. Production worker startup does not run the API lifespan's role/installation verification. A shared worker preflight needs careful integration without operator privileges or claim changes.

Authentication, JWT behavior, subscription/onboarding gates, template definitions and mappings, authorization SQL, campaign dispatch and retry semantics remain untouched.

## Validation evidence and phase gate

Executed:

```powershell
Test-NetConnection localhost -Port 5432 -WarningAction SilentlyContinue -InformationLevel Quiet
Test-NetConnection localhost -Port 6379 -WarningAction SilentlyContinue -InformationLevel Quiet
docker info --format '{{.ServerVersion}}'
.venv\Scripts\python.exe -m pytest -m 'not integration' -q -p no:cacheprovider
```

- PostgreSQL port 5432: reachable. This does not verify credentials, schema, signing keys or RLS installation.
- Redis port 6379: unreachable.
- Docker CLI exists, but Docker engine connection failed. Rechecking outside the sandbox also failed because the Docker Desktop Linux engine pipe was absent. This is not solely a sandbox access failure.
- Pytest selection completed with exit code 0. Authorization sandbox cases were skipped with instructions to use the disposable sandbox runner. One Starlette/httpx deprecation warning appeared. No assertion failures were reported. This is not evidence that database integration or RLS sandbox tests pass.
- No real Meta messages, webhook deliveries, R2 requests, migrations or production operations were performed.
- Existing unrelated tracked cache deletions were present before this work; they were left alone.

Phase 2 cannot pass until local Redis is available and PostgreSQL authorization and worker connectivity are verified. The request explicitly says to report blocked gates instead of advancing; therefore phases 3–7 remain pending. No infrastructure implementation or environment-example changes are represented as completed.

## Resume local validation

Start Docker Desktop with its Linux engine, then verify `docker info` succeeds. With the engine available, a Redis container can be started using loopback-only publishing:

```powershell
docker run --name hanuram-dev-redis -d -p 127.0.0.1:6379:6379 redis:7-alpine redis-server --appendonly yes --maxmemory-policy noeviction
docker exec hanuram-dev-redis redis-cli ping
```

If that named container already exists, inspect it and start it rather than recreating it. Use the existing local PostgreSQL installation and the reviewed checks in `LOCAL_DATABASE_SETUP.md`; do not recreate the database or signing keys. Do not start campaign consumers until the selected environment has been verified as local and uses a designated development sender.

After verifying local role/key installation and Redis:

```powershell
Set-Location 'D:\web apps\Python\CBD_Python'
.\.venv\Scripts\Activate.ps1
# Confirm the local .env follows LOCAL_DATABASE_SETUP.md first.
$env:CAMPAIGN_TRANSPORT = 'celery'
$env:REDIS_URL = 'redis://127.0.0.1:6379/0'
python -m uvicorn app.main:app --reload
# Separate terminals, with the same verified local environment:
python -m celery -A app.tasks.celery_app worker --pool=solo --loglevel=INFO
python -m celery -A app.tasks.celery_app beat --loglevel=INFO
```

The solo pool is the practical Windows development option; Linux production retains its existing worker command. Run exactly one beat scheduler. These commands are preparation instructions, not successful execution claims.

## Modified files report

| File | Modification | Reason | Business logic affected? |
|---|---|---|---|
| `docs/infrastructure_architecture_audit.md` | Added architecture inventory, gaps, validation evidence and resume instructions | Deliver phase 1 audit and report phase 2 blocker | No |

Production deployment, R2 cutover, rollback instructions and separate environment examples must be finalized against the tested implementation after the blocked gate passes. No deployment is authorized or performed by this report.
