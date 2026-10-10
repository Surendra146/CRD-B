# Subscription implementation handoff

Razorpay checkout, provider REST calls, webhook handling, browser SDK loading,
gateway settings and local provider configuration have been removed. Existing
SaaS records, invoice history, CRM and WhatsApp paths remain. Manual operations
require active PlatformStaff membership and explicit subscription permissions.

## Changed backend files (relative to CBD_Python)

- `app/config/settings.py`: remove provider settings.
- `app/models/saas.py`: remove gateway/inbox models and provider plan/subscription
  fields; retain SaaS entities and neutral invoice references.
- `app/services/billing.py`: retain tenant-scoped access/entitlements, enforce
  future starts and expiry, expose effective status and dashboard time predicates.
- `app/services/manual_subscriptions.py` (new): organization locking, target-scope
  validation, assignment/renewal/cancellation, request retry safety, atomic audits.
- `app/services/payment_gateway.py` (removed).
- `app/routers/saas.py`: remove payment mutations/settings/webhook; retain reads,
  consent and onboarding; expose effective subscription status.
- `app/routers/platform.py`: local plan creation, staff subscription read/mutation
  APIs, organization/catalog lookup, correct active dashboard counts.
- `app/routers/__init__.py`: remove the payment webhook router registration.
- `alembic/versions/f91c320ab005_manual_subscriptions.py` (new): drop retired gateway
  and inbox tables/metadata; rename invoice references without deleting history;
  retire subscription write access for the named runtime role. Previous revisions
  were not modified. Downgrade requires a reviewed backup.
- `.env.enterprise.example`, `render.yaml`: remove local provider configuration.
- `scripts/bootstrap_platform_staff.py`: recognize subscription read/manage
  permissions instead of the retired gateway permission.
- `scripts/database_roles.sql`: runtime subscription access becomes read-only.
- `scripts/run_enterprise_tests.py`: add `--no-migrations` test selection.
- `tests/test_subscription_access.py` (new): expiry/start boundaries, invalid
  entitlements and strict manual payload validation.
- `tests/integration/test_manual_subscriptions_api.py` (new): lifecycle,
  authorization, audit rollback/retries, scope isolation, invoice preservation,
  inactive plans/businesses and dashboard counts.
- `tests/integration/test_saas_api.py`: retain shared consent/onboarding/profile
  coverage and replace provider invoice creation with history isolation coverage.
- `tests/integration/test_payment_gateway_api.py`: preserve the frozen historical
  migration test; remove obsolete active-provider behavior tests.
- `tests/integration/test_manual_subscription_migration.py` (new): operator-only
  preservation/RLS/relationship migration coverage, not executed automatically.
- `MANUAL_SUBSCRIPTIONS.md` (new), `PAYMENT_GATEWAY.md`,
  `ENTERPRISE_OPERATIONS.md`, `ENTERPRISE_PHASES.md`: current setup instructions
  and notices identifying superseded historical provider checkpoints.
- `RAZORPAY_REMOVAL_IMPLEMENTATION.md` (this report).

## Changed frontend files (relative to CBD project)

- `src/Pages/Billing.jsx`: staff-managed subscription information, effective
  status, expiry and historical invoice references; remove payment actions.
- `src/Pages/Platform.jsx`: local plan fields, manual subscription panel; preserve
  existing tenant management, onboarding and audit UI.
- `src/components/Platform/ManualSubscriptions.jsx` (new): permission-gated target
  selection and assignment, renewal and cancellation forms with a required reason.
- `src/services/saas.js`: replace provider methods with staff subscription APIs.
- `src/services/manualSubscriptions.js` (new): preserve request IDs on failed
  unchanged retries within the mounted console session.
- `src/services/paymentCheckout.js` (removed).
- `tests/paymentCheckout.test.js` (removed).
- `tests/manualSubscriptions.test.js`, `tests/subscriptionPages.test.js` (new):
  retry safety, customer history/status rendering and staff control visibility.
- `docs/PAYMENT_GATEWAY.md`: describe the current manual flow.
- `docs/ENTERPRISE_SAAS_REVIEW.md`, `docs/SAAS_DELIVERY_STATUS.md`,
  `docs/IMPLEMENTATION_CHECKPOINT.md`: identify superseded historical workflows.

Other pre-existing modifications and unrelated untracked files were preserved.
No dependency manifest change was necessary: neither application used a dedicated
provider SDK package. Previous migrations and historical schema dumps still
contain provider references as historical artifacts.

## Validation and remaining operator work

Backend: 199 tests passed with one existing Starlette deprecation warning;
migration-executing and forced-RLS suites were excluded as instructed.
Frontend: 10 tests passed, Vite production build passed, ESLint passed. Page checks
render real React components with seeded query data; no live browser/database
application interaction was attempted. Backend tests use a dedicated `*_test`
database and exclude every known test that invokes migration functions.

The new migration, migration preservation test and forced-RLS suites have not
been executed. No database reset, Git push or deployment was performed.

Follow [MANUAL_SUBSCRIPTIONS.md](MANUAL_SUBSCRIPTIONS.md) to back up/review the
migration, apply revision `f91c320ab005` manually, verify runtime/control role
grants, explicitly grant staff permissions and review legacy subscription dates.
Restart both updated applications after the migration. Remove any external
provider secrets/webhook configuration manually. No existing external recurring
payments have been cancelled by this local change.
