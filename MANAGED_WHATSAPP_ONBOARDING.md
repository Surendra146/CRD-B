# Admin-managed WhatsApp onboarding

This change extends the existing HanuRam onboarding request table and SaaS APIs. Tenants submit assistance requests; authorized platform staff accept, reject, start, request tenant action, verify, and connect. A tenant can authorize Meta only during an administrator-requested `meta_authorization` action. Authorization saves a provisional connection; it does not enable messaging.

## Subscription and authorization rules

Acceptance uses `billing.effective_status` and the assigned plan's existing positive integer `whatsapp_numbers` entitlement. No new subscription system or subscription status snapshot is stored. Missing, expired, cancelled, future-start, or otherwise inactive subscriptions return HTTP 409 with `detail.code` and `detail.message`; an active plan without WhatsApp numbers returns `WHATSAPP_ENTITLEMENT_REQUIRED`.

The gate runs again for setup, connection activation, and messaging through an onboarding-managed sender. Existing connections without onboarding records retain their existing deployment subscription-enforcement setting. Production should keep `ENFORCE_SUBSCRIPTION=true`.

Organization row locks use the same order as manual subscription management, so acceptance and plan changes serialize. Request row locks and a partial unique index prevent conflicting acceptance and duplicate active requests. Subscription records are never modified by onboarding. Staff actions still require explicit `onboarding.manage` membership and signed control-database authority. Viewing or changing subscriptions retains `subscriptions.read` / `subscriptions.manage` permission requirements.

Meta verification uses existing encrypted credentials and provider services to check authorized WABA/phone assets, approved-number match, required scopes, the WABA app subscription, and an active application messages webhook. A consented recipient and an approved template without parameters are required for the explicit test-send action. Connection activation requires that the existing signed webhook has recorded that test as delivered or read. Test acceptance alone is insufficient. Verification expires after 30 minutes and is invalidated by connection or setup changes. Repeated identical verification within that window reuses an accepted/delivered test rather than sending again; a failed test can be retried. Provider errors never store credentials or raw provider responses.

Subscription expiry preserves the technical connection and history while blocking activation or sending. No Meta assets are deleted. Tenants confirm actions without changing onboarding status; administrators review and resume setup.

## Frontend files

- `src/Pages/Business.jsx`: uses the assistance workflow in Business settings.
- `src/Pages/CLC/Settings.jsx`: uses the same workflow in CRM settings.
- `src/Pages/Platform.jsx`: replaces the arbitrary status selector with the managed queue.
- `src/components/Platform/ManualSubscriptions.jsx`: selects the queue request's organization when opening subscription management.
- `src/components/Platform/WhatsAppOnboardingQueue.jsx` (new): search, status/subscription filters, pagination, details/timeline, controlled actions, subscription/success dialogs, and verification panel.
- `src/components/whatsapp/WhatsAppSetupAssistance.jsx` (new): country-code/number validation, request form, duplicate suppression, instructions, tenant confirmation, and connected information.
- `src/components/whatsapp/WhatsAppOnboardingProgress.jsx` (new): optional-action progress tracker.
- `src/components/whatsapp/WhatsAppConnectionCard.jsx`: administrator-requested authorization UI; removes direct tenant connect actions.
- `src/services/onboarding.js` (new): phone validation, queue filtering, status labels, and subscription dialog selection.
- `src/services/saas.js`: adds confirmation and verification calls.
- `tests/onboarding.test.js` (new), `tests/subscriptionPages.test.js`: validation, dialogs, filtering, and component rendering.
- `.gitignore`: excludes the temporary backend staging directory.

## Backend files

- `app/models/saas.py`: extends `OnboardingRequest` with administrator IDs, timestamps, instructions/action metadata, rejection reason, history, evidence, and the active-request index.
- `app/services/onboarding.py` (new): lifecycle, effective subscription gate, Meta checks, delivery-gated activation, and safe history.
- `app/routers/saas.py`: request validation/deduplication, confirmation, and computed WhatsApp subscription eligibility.
- `app/routers/platform.py`: existing staff update endpoint now enforces transitions; adds verification and enriched queue details.
- `app/routers/whatsapp_connections.py`: restricts authorization endpoints to administrator-requested tenant action; number matching and provisional status.
- `app/services/whatsapp_connections.py`: blocks provisional sending and revalidates messaging eligibility.
- `app/database/tenancy.py`: requires reviewed schema revision `f91c320ab009` at enterprise startup.
- `alembic/versions/f91c320ab009_managed_onboarding.py` (new): additive fields, preserved legacy state history, uniqueness, and narrowly scoped policy extensions.
- `scripts/run_authorization_sandbox.py`: tests the new migration head in the disposable cluster.
- `tests/test_managed_onboarding.py` (new): subscription/state/verification/security cases.
- `tests/test_whatsapp_connections.py`, `tests/integration/test_saas_api.py`, `tests/integration/test_manual_subscriptions_api.py`, `tests/integration/test_whatsapp_connections_api.py`: adapt existing regressions to the managed lifecycle.
- `tests/security/test_authorization_roles.py`: exercises acceptance races, real restricted-role policies, provisional sending, signed delivery activation, and queue access.
- `MANAGED_WHATSAPP_ONBOARDING.md` (new): copy of this implementation/deployment guide.

## API changes

Existing routes are reused; no duplicate API family was created.

| Route | Behavior |
| --- | --- |
| `POST /api/saas/onboarding` | `{business_name, phone}`; `phone` is international digits including the country code. No active subscription is required to request help. Duplicate active/connected requests return 409. |
| `GET /api/saas/onboarding` | Tenant-scoped request history, progress, instructions, and connection evidence. |
| `POST /api/saas/onboarding/{id}/verification-completed` | New; idempotent tenant confirmation without activation. |
| `GET /api/saas/subscription` | Adds computed `whatsapp_eligible` to existing subscription data. |
| `GET /api/platform/onboarding` | Existing staff queue enriched with tenant/organization names and effective eligibility. Frontend search, filtering, and pagination operate on this snapshot. |
| `PATCH /api/platform/onboarding/{id}` | Existing endpoint accepts controlled `status`, optional `customer_message`, optional `required_action`. `ready` and legacy skip-step statuses are no longer accepted. Subscription failures return structured 409 errors. |
| `POST /api/platform/onboarding/{id}/verify` | New; `{test_phone, template_name, language}`. Sends an explicitly requested, consented test using an approved template. Saves evidence but keeps setup in progress. |
| `POST /api/whatsapp-connection/{start,exchange,select}` | Existing Meta infrastructure now requires an eligible, administrator-requested authorization action. Selection must match the approved number. |
| `GET /api/whatsapp-connection/` | Adds `authorization_saved`; `connected` stays false while an onboarding-managed connection is provisional. |

Main transitions: `requested -> accepted -> setup_in_progress -> connected`; `setup_in_progress -> action_required -> setup_in_progress` is optional. Rejection requires a reason; supported failure/cancellation transitions also require an explanation. Rejected/failed/cancelled requests allow a new assistance request after administrator review. History remains on previous records.

## Tests and limits

- Frontend: 22 tests passed; production build passed; ESLint passed for all changed frontend source files.
- Backend PostgreSQL regression suite: 260 tests and 6 subtests passed in the disposable PostgreSQL 18 cluster.
- Restricted-role suite: 34 tests passed, including concurrency, signed webhook delivery, startup validation, and tenant isolation.
- Migration chain through `f91c320ab009` successfully executed as a NOSUPERUSER/NOBYPASSRLS installation operator.
- One existing Starlette/httpx deprecation warning remains.
- No real Meta account, authorization, recipient, or message was used. Provider behavior was mocked; an actual Meta integration still needs staging validation with official credentials and an explicitly consented recipient.
- Browser automation could not initialize in this session. Component rendering, validation tests, lint, and build verification passed; visual browser QA remains advisable.
- The notification endpoint currently returns an empty list; there is no delivery service to reuse. Tenant and staff panels poll for updates every 30 seconds. Email/WhatsApp notification delivery is not implemented.
- Queue pagination currently occurs in React using the existing queue snapshot. Large installations may need server pagination and batched eligibility queries.
- The supplied attachment contained written requirements, with no infographic image to compare visually.

## Safe migration and Render deployment

Do not deploy the changed frontend against the old backend. Coordinate backend migration/code and frontend release; enterprise startup deliberately fails if revision 009 is missing.

1. Review both repository diffs and back up PostgreSQL using the existing backup procedure. Disable automatic deploy while coordinating the change. Never reset tables or stamp Alembic to bypass a missing revision.
2. Review active-request duplicates and legacy onboarding states with an authorized staff/operator session. The new index allows one request per organization in requested/accepted/setup/action-required/connected states. Legacy `needs_customer_action`, `provider_review`, `billing_pending`, and `ready` become `requested`; their original status is saved in history. They require acceptance and fresh verification. Existing Meta credentials are retained. Any organization with multiple resulting active requests causes the whole migration to roll back; reconcile them through a reviewed data-preserving process before retrying.
3. Test a staging database copy. Run `python scripts/run_authorization_sandbox.py --legacy-tests` on a Windows host with PostgreSQL binaries (or pass `--postgres-bin` for their location). This runner never uses existing PostgreSQL services/databases.
4. Use the existing separate migration/operator login and existing provisioned database signing keys. Revision 009 retains FORCE RLS and runtime/control role separation. Its temporary data-migration policy applies only to the installation operator and is removed in the same transaction. New control reads are confined to the selected organization; onboarding cannot mutate billing. No additional environment variables are required.
5. After approving the reviewed migration, run `python -m alembic upgrade f91c320ab009` with the existing `MIGRATION_DATABASE_URL` in the backend's deployment environment. Check `python -m alembic current` reports `f91c320ab009` before restarting the backend. Do not run the migration from a runtime/control connection. Automated downgrade is deliberately refused because it would drop verification/history fields; rollback needs a reviewed data-preserving migration or backup recovery.
6. Deploy backend code through the existing reviewed Render process, then frontend code. Keep existing Meta application ID/secret, signup configuration ID, encryption key, Graph version, signed-webhook secret/verify token, CORS origin, runtime/control URLs, and database authorization keys. Keep `REQUIRE_RLS=true`, `AUTO_CREATE_TABLES=false`, and production subscription enforcement enabled.
7. Smoke-test tenant request, duplicate prevention, inactive/no-entitlement popups, eligible acceptance, rejection, tenant authorization, confirmation, verification, signed test delivery, connected state, expired-plan sending denial, and CRM/authentication. Never run a real test-send without the recipient's consent. Review legacy requests before restoring their messaging access.

Meta verification follows [Meta's WhatsApp Cloud API collection](https://www.postman.com/meta/whatsapp-business-platform/documentation/wlk6lh4/whatsapp-cloud-api). Local mocks and tests are not evidence of a live Meta connection.

## Git review and commit

From the frontend directory:

```powershell
git status --short
git diff --check
git diff -- src tests .gitignore
git add .gitignore src/Pages/Business.jsx src/Pages/CLC/Settings.jsx src/Pages/Platform.jsx src/components/Platform/ManualSubscriptions.jsx src/components/Platform/WhatsAppOnboardingQueue.jsx src/components/whatsapp/WhatsAppConnectionCard.jsx src/components/whatsapp/WhatsAppOnboardingProgress.jsx src/components/whatsapp/WhatsAppSetupAssistance.jsx src/services/onboarding.js src/services/saas.js tests/onboarding.test.js tests/subscriptionPages.test.js docs/managed-whatsapp-onboarding.md
git commit -m "Add admin-managed WhatsApp onboarding UI"
```

From the backend directory, after applying the reviewed files:

```powershell
git status --short
git diff --check
git diff -- app alembic scripts tests
git add app/models/saas.py app/services/onboarding.py app/routers/saas.py app/routers/platform.py app/routers/whatsapp_connections.py app/services/whatsapp_connections.py app/database/tenancy.py alembic/versions/f91c320ab009_managed_onboarding.py scripts/run_authorization_sandbox.py tests/test_managed_onboarding.py tests/test_whatsapp_connections.py tests/integration/test_saas_api.py tests/integration/test_manual_subscriptions_api.py tests/integration/test_whatsapp_connections_api.py tests/security/test_authorization_roles.py MANAGED_WHATSAPP_ONBOARDING.md
git commit -m "Enforce managed WhatsApp onboarding and subscription gates"
```

These commands are for review and optional manual commit. No push or deployment has been performed. Existing unrelated tracked cache deletions and `migration_review.sql` in the backend must not be included in this feature commit.
