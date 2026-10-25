# Template media storage integration

## Audit and scope

The existing adapters were not connected to template media. `template_media.py` directly used local paths, while the API and worker already shared `asset()`, `sample_handle()` and `sending_media()`. The integration now routes storage reads/writes through the existing factory. No schema migration is required. Asset IDs, workflow JSON fields, local directory layout, file validation and provider payloads are unchanged.

Existing settings/requirements edits and adapter files were present before this task and were retained. `render.yaml` already defines web, Redis, worker and beat; no infrastructure duplication is needed. Authentication, RLS, RBAC, onboarding, dispatch and scheduling code were not changed. Template deletion still retains files; no new automatic deletion policy was introduced. Queued templates and historical approvals retain their existing ownership/version checks.

## Behavior and security

- Keys are server-derived ASCII numeric tenant/organization/template IDs followed by a 32-character lowercase hex asset UUID. Both adapters share validation. The local layout remains `{tenant_id}/{organization_id}/{template_id}/{asset_id}`.
- Local reads/deletes resolve paths and enforce containment, including symlinks and Windows junctions. Writes use exclusive creation. Keep this application-owned root unwritable by untrusted processes; path checks do not provide isolation from a hostile process racing filesystem operations.
- R2 uses HTTPS, Signature V4, server-only credentials, five-second connect and 30-second read timeouts, standard retries with at most three total attempts. Uploads use `IfNoneMatch='*'` to prevent overwriting existing objects. R2 supports atomic conditional creation: [Cloudflare S3 extensions](https://developers.cloudflare.com/r2/api/s3/extensions/).
- Both adapters limit stored/read bytes to 100 MiB; application image/video/document limits remain stricter where applicable. SHA-256 is checked before preview, sample upload and worker upload. Existing processing still buffers bounded complete files; this change does not implement end-to-end streaming.
- Missing/corrupt media preserves the existing HTTP 409 behavior. Upload storage failures return a generic 503. Provider permission, connection and timeout errors are sanitized; there is no local fallback from R2.
- Private preview continues through the authenticated API, with existing tenant/org checks and private/no-store headers. No object keys or credentials are added to responses. No public URLs or presigned URLs are needed for the existing Meta upload flow.

## Database failure handling

Upload validates bytes, creates a new UUID object, adds the unchanged metadata, explicitly flushes and commits. A failed flush or confirmed constraint/data rejection triggers rollback and best-effort deletion of only that new object. Previous objects are never cleaned up by this path.

A generic commit failure may mean the database committed before losing its connection. In that case the object is retained and a safe diagnostic records template/asset identifiers for reconciliation. Rollback and cleanup failures are logged without exception text, SQL or credentials. An ambiguous storage PUT, interrupted filesystem write or process crash can also leave an orphan: reconcile later rather than deleting based on an uncertain outcome. This is not a distributed atomic transaction.

## Configuration

Local development:

```ini
MEDIA_STORAGE_BACKEND=local
WHATSAPP_TEMPLATE_MEDIA_ROOT=.template-media
```

API and worker must use the same absolute root, or start from the same repository directory. Relative paths resolve from the process working directory.

Render web and campaign worker (and beat, which imports shared settings):

```ini
MEDIA_STORAGE_BACKEND=r2
R2_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
R2_BUCKET_NAME=<private-bucket-name>
R2_ACCESS_KEY_ID=<server-only-access-key>
R2_SECRET_ACCESS_KEY=<server-only-secret>
```

These are the actual supported settings. `R2_ACCOUNT_ID` is not a separate setting: it is part of the endpoint URL. All R2 fields are required when selecting `r2`. Keep runtime/control database URLs, authorization signing keys, Meta application credentials and encryption keys as currently configured; do not put operator migration credentials into runtime services. Do not put R2 credentials in Vite variables or frontend configuration.

## Cloudflare and Render preparation

1. Create a dedicated private R2 bucket. Leave public development URLs and custom public domains disabled. No public ACL or browser CORS is needed for server-to-server storage.
2. Create credentials restricted to object read/write access on that bucket, sufficient for put/get/delete. Keep bucket administration separate. Store credentials only in server-side Render secret settings.
3. Inventory and copy existing media using the procedure below before enabling R2. The code does not migrate existing media and does not fall back to legacy files.
4. Configure the same bucket/endpoint/credentials/backend on web, worker and beat. Review existing Render resources manually; do not sync a new blueprint merely to set these values.
5. Perform the cutover during a controlled upload/dispatch pause so mixed storage configurations cannot create inaccessible objects. Keep existing health checks; `/ready` currently checks PostgreSQL/Redis, not R2.
6. Validate authenticated image/PDF/video upload and preview, invalid-file rejection, isolation, and mocked provider/worker behavior in staging. A real R2 smoke test remains an explicitly authorized external check. Verify ffprobe is installed for MP4 validation.
7. Resume processing only after all consumers use the same verified backend. Do not start additional beat schedulers.

## Existing media migration plan (not executed)

No live migration utility is included. Approve any live migration separately.

1. Inventory database `workflow.assets`, approved-history references and campaign snapshot asset references under reviewed authorized/operator access. Inventory source files from the existing root. Report missing references, orphan files and invalid keys separately; never treat absence from one tenant-scoped query as proof of orphanhood.
2. Produce a dry-run report with key, tenant/org/template/asset IDs, expected byte count and SHA-256, source availability and destination status. Exclude credentials and media bytes. Preserve identifiers exactly.
3. Copy valid referenced files using create-only PUT. If a destination already exists, read and verify size/hash; identical content is a successful safe retry, differing content is a conflict requiring review. Never overwrite it.
4. Read every copied object back and verify both size and SHA-256 against database metadata. Record copied/verified/skipped/missing/conflicting/failed counts and per-object outcomes in a migration report.
5. Pause uploads and dispatch for a final delta inventory/copy/verification. Resolve every required missing or conflicting reference before setting production to R2. Retain all local source files and the reports.
6. Rollback before new R2 writes can restore the previous shared local configuration. After new R2 writes, first reconcile those objects and database references back to the old root and verify them, or keep R2 while reverting code. A blind backend toggle would strand new uploads. A code version that directly reads local files also requires this reconciliation.

## Files changed

| File | Change | Business logic affected? |
|---|---|---|
| `app/services/template_media.py` | Factory-based read/write, safe keys, unchanged metadata and integrity check; local compatibility helper | No |
| `app/services/media_storage/keys.py` | Shared key validation and byte limit | No |
| `app/services/media_storage/local.py` | Containment, bounded reads/writes, exclusive creation | No |
| `app/services/media_storage/r2.py` | Endpoint validation, bounded requests, create-only uploads and sanitized failures | No |
| `app/routers/templates.py` | Upload transaction rollback/cleanup and ambiguous-commit retention | Infrastructure failure responses only |
| `tests/conftest.py` | Force test local storage; isolate roots/settings from live `.env` | No |
| `tests/test_media_storage_r2.py` | Retain tests, assert conditional creation | No |
| `tests/test_media_storage_integration.py` | Adapter/HTTP/failure/worker-media tests with mocked services | No |
| `docs/r2_media_storage.md` | Configuration, migration, rollout and rollback procedure | No |

## Validation

Compilation of `template_media.py` and the storage package passed. Focused tests:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_media_storage_r2.py tests/test_media_storage_integration.py tests/test_template_workflow.py -q --basetemp=.\test-temp --tb=short
```

Result: **105 passed**, one pre-existing Starlette/httpx deprecation warning. This includes Windows junction containment, both storage adapters, HTTP upload/preview, tenant/org denials, integrity, bounded reads, provider failure sanitization, transaction cleanup and retention, mocked approval samples and send-time uploads. The earlier broader non-integration run passed **332 tests and six subtests**, skipped 35 sandbox-only cases and deselected 104 integration cases; four additional scope-denial tests were added and passed in the final focused run.

The initial five PostgreSQL lifecycle cases failed at setup because the existing local test database credentials were rejected. No credentials were changed. The existing authorization sandbox then passed **35 authorization tests** on its own disposable cluster. Its first legacy-suite attempt hit the inaccessible default Windows pytest directory (427 setup errors); this was diagnosed with a single test. Use an explicit workspace base directory when invoking that runner:

```powershell
$env:PYTEST_ADDOPTS = '--basetemp="D:/web apps/Python/CBD_Python/test-temp-sandbox-r2" --tb=short'
.venv\Scripts\python.exe scripts/run_authorization_sandbox.py --legacy-tests
Remove-Item Env:PYTEST_ADDOPTS
```

Database lifecycle tests require a dedicated `*_test` PostgreSQL database; their fixture creates and drops only a disposable schema. The existing sandbox runner creates its own temporary cluster and generated credentials instead of using configured database credentials. Mocked HTTP checks use real routes and adapters with an injected database session. No live R2 operations, Meta delivery, production migration, campaign workers, deployment or push were performed.

Final rerun with the explicit workspace base directory succeeded: **35 authorization sandbox tests passed**, followed by **427 legacy/unit/API tests and six subtests passed** in 55.56 seconds. The latter run includes the five template lifecycle cases, the focused storage tests and campaign regressions; it excludes the four migration-oriented modules selected out by the existing `--no-migrations` runner. One existing Starlette/httpx deprecation warning remains. The disposable PostgreSQL cluster was stopped and removed. Scoped `git diff --check` passed; existing CRLF conversion notices are informational.

| Completion gate | Result |
|---|---|
| A: Code | Passed: local/R2 factory integrated; metadata and successful HTTP contracts preserved |
| B: Security | Passed automated checks: scoped access, keys, bounded reads, integrity, junction containment, safe errors |
| C: Tests | Passed final focused and disposable-database runs; earlier environmental setup failures resolved by isolated credentials and explicit temp directory |
| D: Integration | Passed upload/preview, template lifecycle, mocked approval and worker media retrieval/delivery checks |
| E: Deployment preparation | Configuration, copy verification, deployment and rollback procedures documented; live R2 smoke test and production cutover remain unperformed |
