# WhatsApp sending interlock

Implemented 2026-10-25. This supersedes earlier readiness statements that there is no application sending switch. No production setting, database, deployment, broker or Meta account was modified.

## Configuration and deployment

`WHATSAPP_SENDING_ENABLED=false` blocks message delivery. Unset, empty, misspelled and other values fail closed; only case-insensitive, whitespace-trimmed `true` enables it. It is a server setting, never a Vite/client option. The `.env.example` includes the safe value. Existing test regressions explicitly opt in to mocked sending in `tests/conftest.py`; new tests explicitly exercise both states. No test uses a real provider.

| Render service | Storage-only deployment | After explicit sending authorization |
|---|---|---|
| `cbd-backend` | `WHATSAPP_SENDING_ENABLED=false` | `true` |
| `hanuram-campaign-worker` | `false` | `true` |
| `hanuram-campaign-beat` | `false` | `true` |

Use the same value everywhere. Beat currently publishes periodic task envelopes; the worker executing `publish_due` enforces the flag before database discovery/claim or delivery-task publication. Beat's own setting does not control a worker configured differently. Existing R2, database/key configuration and `CAMPAIGN_TRANSPORT=celery` remain as documented in `r2_render_deployment_readiness.md`; the interlock also protects the alternative database scheduler. Do not change transport to pause sends.

Settings are cached per process. Changing Render environment variables is not an instantaneous distributed kill signal: coordinate pause/drain and restart **all** web and worker instances. Old code/processes without this interlock can still send. A guard cannot recall in-flight HTTP requests already submitted to Meta. To guarantee a fully frozen window, stop/drain producers and consumers and reconcile in-flight sends as well as deploying this setting consistently. Do not enable sending to diagnose storage.

No worker/Beat startup, configuration change, deployment or messaging authorization is implied by this document. Before enabling, explicitly review queued work, recipient consent/subscriptions, tenant sender credentials, outstanding leases and ambiguous delivery evidence. Keep the production RLS, RBAC and webhook settings enabled.

## Every discovered delivery path

| Path | Guard/disabled behavior |
|---|---|
| Direct communications routes `/whatsapp`, `/whatsapp/send` and communication alias | `send_whatsapp` raises a dedicated HTTP 503 before credential resolution, media hydration, provider call or success recording. Existing route auth dependencies remain. |
| New bulk/scheduled campaign submission | `send_bulk_whatsapp` raises 503 before building/persisting a job or outbox. It does not report success or accumulate new silently pending requests. Client may retry after explicit authorization. |
| Shared campaign dispatch | `dispatch_bulk_job` checks at entry and immediately before each queued recipient's durable uncertainty write. |
| Normal final provider boundary | `meta_whatsapp.send_message` checks before building the Meta `/messages` request, independently of caller checks. Covers text, interactive, public-URL media and approved template messages. |
| Celery `deliver_job` | Returns before sessions/claims when disabled. A mid-dispatch disabled exception is handled separately from delivery failure: no recipient failure conversion and no outbox completion. |
| Celery `publish_due` / PostgreSQL outbox recovery | Returns before DB access/claims when disabled; RLS claim loop rechecks the flag. Durable PostgreSQL jobs/outbox remain recoverable. |
| Database scheduler | `dispatch_due_job` returns false before sessions/claims when disabled. If dispatch is blocked after a legacy non-RLS scheduler claim, restores `in_progress` to `scheduled`, without overriding concurrent paused/cancelled state. RLS branch uses the guarded delivery task. |
| Managed onboarding verification test message | Explicit guard immediately before the real verification message; no new MessageRecord/success evidence on blocked delivery. Previously accepted reusable evidence can still be reused without sending. Non-message eligibility/provider checks remain available. |
| Generic Meta `graph` helper | POST paths ending `/messages` independently check the flag before network access, covering the onboarding helper's second message boundary. Other graph operations remain unchanged. |

Repository search found message delivery at `meta_whatsapp.send_message` and the onboarding `/messages` POST through `whatsapp_connections.graph`. No discovered delivery path is intentionally left unguarded. New future low-level HTTP integrations must use these guarded boundaries or add equivalent checks; this is not a firewall for arbitrary code or third-party processes.

## Pending work, restart and idempotency

Disabled worker tasks may acknowledge their broker envelopes without consuming a database claim. The PostgreSQL job/outbox remains scheduled/in-progress and pending/published. After enablement, the existing periodic publisher/claim machinery rediscovers it; no new Redis queue or synthetic delivery success is introduced. Existing RLS job leases may postpone eligibility for up to their existing 30-minute lifetime. Do not delete leases or manufacture claims to force immediate resumption. Existing paused/cancelled/failed jobs are not automatically reset by this feature.

If the dedicated disabled exception occurs after the campaign wrote `unknown` for the current queued recipient but before sending, only that recipient is restored to its original queued metadata. This exception is generated solely by checks before a provider message request. Existing `unknown` recipients from actual ambiguous network attempts are never reset or retried; accepted/sent/delivered/read recipients are skipped as before. Generic provider errors still use existing failure/uncertainty handling. Worker outbox completion is skipped on a disabled exception.

The feature preserves existing advisory locks, claim scope checks, sender validation, active creator/tenant checks, subscription/consent enforcement, webhook signatures and RLS. It does not promise exactly-once delivery. A process crash between writing uncertainty and calling Meta can still leave `unknown`; the existing conservative no-automatic-retry rule remains.

## Operations intentionally not disabled

- Webhook verification, signature validation, delivery-state updates and inbound consent processing.
- Template listing/synchronization, approval submission, and sample media uploads. These can still make real Meta API calls; the switch is not a blanket ban on external requests.
- Local/R2 asset uploads, private preview and storage cleanup behavior; Meta media uploads are also not message delivery.
- Onboarding configuration, discovery and authorization checks. Only its explicit test-message send requires enablement.
- Database/RBAC/subscription/consent checks are not weakened. An enabled send must still pass them.

## Files changed for this feature

`app/config/settings.py`, new `app/services/whatsapp_interlock.py`, `app/services/meta_whatsapp.py`, `app/services/whatsapp_connections.py`, `app/services/onboarding.py`, `app/routers/communications.py`, `app/tasks.py`, `app/services/whatsapp_scheduler.py`, `.env.example`, `tests/conftest.py`, new `tests/test_whatsapp_interlock.py`, webhook flag parameterization in `tests/test_whatsapp_delivery.py`, this report, and a historical-status note in the R2 readiness report. No schemas/migrations or production environment files changed. Other pre-existing storage/settings edits were retained.

## Validation and remaining risks

Focused new tests: **24 passed**. They cover default/invalid/true values, final provider boundary, all direct route aliases, bulk rejection without persistence, graph-operation separation, disabled worker/publication/scheduler with no claims, re-enabled claim/publication, worker/outbox resume, mid-dispatch blocking without outbox completion, queued-only recipient resume after settings reload, ambiguous/delivered recipient preservation and onboarding test-message blocking. These directly invoke task functions with mocks; no Celery consumers are started.

Earlier non-integration regression run after the implementation: **340 passed, 35 skipped, 104 deselected, six subtests passed**. The sandbox-only skips are not proof of RLS verification. Subsequent focused send/scheduler/onboarding run: **79 passed**. After adding both enabled/disabled signed-webhook cases, focused interlock/delivery checks: **36 passed**, including invalid-signature rejection with the flag off.

Final disposable PostgreSQL sandbox: **35 authorization tests passed**, followed by **455 unit/API/regression tests and six subtests passed** (58.81 seconds for the latter). This uses `scripts/run_authorization_sandbox.py --legacy-tests`, which excludes its existing migration-oriented modules from the legacy run. Its separate authorization cluster exercises the real migration/security chain. Both temporary databases were stopped/removed by the runner. Python compilation and scoped `git diff --check` passed. Existing Starlette/httpx deprecation warning remains. No production state or installed Render configuration was verified.

The first sandbox attempt had three failures caused by unavailable external Redis rate limiting. The successful rerun set `ENABLE_DISTRIBUTED_LIMITS=false` **only in the isolated local test process**, retained FORCE RLS/authorization and used generated DB credentials. Sending was explicitly enabled in that process for existing mocked provider tests; production defaults remain false. No production variables were changed. Example local-only regression invocation:

```powershell
# Local disposable sandbox and mocked provider tests only; never a Render command.
$env:WHATSAPP_SENDING_ENABLED = 'true'
$env:ENABLE_DISTRIBUTED_LIMITS = 'false'
$env:PYTEST_ADDOPTS = '--basetemp="D:/web apps/Python/CBD_Python/test-temp-interlock-sandbox" --tb=short'
.venv\Scripts\python.exe scripts/run_authorization_sandbox.py --legacy-tests
```

Use a dedicated test shell and close it afterward; do not reuse those overrides for running application services.

Remaining operational risks: inconsistent/stale process flags, already in-flight HTTP sends, pre-existing old-code workers, lease-delayed resumption, durable queued work starting immediately after later authorization, and the existing crash/uncertainty window. Flag-off only affects delivery; unrelated Meta operations can still execute. The switch is not a distributed live feature-flag service and does not replace controlled deployment, queue review or authorization to send.
