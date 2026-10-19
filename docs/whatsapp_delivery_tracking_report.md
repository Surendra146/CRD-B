# WhatsApp onboarding delivery tracking

## Findings

Confirmed from code: onboarding saves Meta's message ID and initial acceptance in
`OnboardingRequest.verification`, and creates a scoped `MessageRecord`. Signed
webhooks already updated message status, but discarded message-record failure
details and receipt timestamps. The onboarding API returned its original JSON
snapshot rather than the latest record. The UI enabled connection after acceptance,
although the backend already required delivered/read, current connection evidence,
and an active eligible subscription. The 30-minute response-retry guard reused
accepted/sent/successful tests without communicating reuse.

Unknown: why the pictured recipient did not receive the message. Production webhook
events and provider failure details were not available. Configuration checks do not
prove a callback arrived. These changes improve tracking; they do not prove delivery
or fix an unobserved Meta/account/recipient problem.

## Changes and files

Backend:

- `app/models/saas.py`: message-record JSONB `delivery_details`.
- `alembic/versions/f91c320ab011_message_delivery_details.py`: additive column with
  an empty-object default; existing rows and RLS policies remain in place.
- `app/routers/webhooks.py`: retain delivery details and callback receipt time;
  safely return 503 on database processing errors so Meta can retry. Logs contain
  a fixed diagnostic, without SQL, credentials or webhook bodies.
- `app/services/meta_whatsapp.py`: retain sent/read and status-update timestamps,
  using the existing monotonic status/timestamp ordering and campaign processing.
- `app/services/onboarding.py`: project current message status and diagnostics into
  API responses, distinguish API acceptance from callback receipt, scope correlation
  by tenant/organization/sender/recipient/message ID, and enforce a one-minute send
  cooldown. Same recent accepted/sent/delivered/read test is reused for 30 minutes.
  Failed tests can be retried after the cooldown; stale tests after the reuse window.
- `app/routers/platform.py`: return `test_action` (`sent` or `reused`); preserve the
  last correlated message when a subsequent provider check fails.
- `tests/test_onboarding_delivery_tracking.py` and
  `tests/test_managed_onboarding.py`: delivery tracking and validation regressions.

Frontend (under `D:\web apps\React\CBD project`):

- `src/components/Platform/WhatsAppOnboardingQueue.jsx`: message diagnostics,
  configured/received webhook indicators, provider failure details, manual refresh,
  delivered/read connection gating, and explicit reuse feedback.
- `src/services/onboarding.js`: delivery explanations and bounded polling policy.
- `tests/onboarding-delivery.test.js`: status gating and polling tests.

The shared onboarding query polls every 10 seconds while a setup test is accepted
or sent and under 30 minutes old. It stops on terminal status, timeout or loss of
query observers; background polling is disabled. Existing React Query caching
coalesces requests. Manual refresh remains available.

## Webhook processing and security

GET verification and POST HMAC authentication remain intact. Existing WABA/phone
lookup and signed database authority select the connection. Record correlation
uses message ID plus tenant, organization and sender. Unknown message IDs are
ignored while campaign processing continues. Updates are locked, duplicate events
do not change the effective state, and older/lower-ranked events cannot regress
successful delivery. Last receipt time advances on retries. Failure details are
retained; delivered/read events clear an earlier failure through the existing reducer.

No RBAC, consent, subscription checks, RLS policies, login roles or authorization
keys were weakened. The migration adds a column to an already protected table;
existing table-level permissions apply. Real PostgreSQL RLS verification is still
required in staging because the configured local integration database rejected login.

## Validation

- Final focused backend run: **58 passed, 0 failed**.
- Broader backend run before the last six focused test additions: **225 passed,
  1 failed, 34 skipped**, plus 6 passed subtests. The failing local-authorization
  setup test concerns existing database/operator configuration; its files were
  not changed. Disposable security tests require their separate sandbox runner.
- Full backend integration run: blocked at setup by local test-database password
  authentication failure. No production connection or migration was attempted.
- Frontend: **34 passed, 0 failed**.
- Frontend ESLint: passed.
- Production build: passed. An earlier overlapping build encountered output-folder
  permissions; the subsequent normal build and isolated output build succeeded.
- Browser interaction tests and a real Meta delivery have not been performed.

## Manual migration and Render deployment

1. Review both repository diffs and back up the intended database. Keep existing
   unrelated authorization-script edits separate.
2. First test on staging using its authorized migration-operator credentials and
   the existing database authorization setup. Confirm the current revision and
   migration chain with `alembic current` and `alembic heads`.
3. Review the additive revision `f91c320ab011`. During the approved deployment
   window, an operator can run `alembic upgrade f91c320ab011` against the intended
   database. This command was **not executed** by this task.
4. Deploy the backend only after the column exists, then deploy the frontend with
   its existing build settings. No environment variable changes are required.
5. Verify the existing Meta callback URL, messages subscription and POST delivery
   in Render logs without publishing secrets. Confirm the API serves the new fields.
6. If reverting application code, leave the additive column in place. Migration
   downgrade drops diagnostics and should only be considered after data review.

## Real-message verification

1. With an active eligible subscription, authorize the correct business sender and
   record consent for the recipient. Confirm the template/language is approved.
2. Send one permitted test. Record its message ID. Expect API acceptance, pending
   delivery, callback receipt No, and a disabled connection button initially.
3. Repeat the same request within 30 minutes: expect reuse and the same message ID.
4. Observe the signed callback: sent remains pending; delivered/read enables the
   button. Confirm the record's timestamps and callback indicator update.
5. If failed, examine the actual Meta code/message/details, correct that provider
   issue, and retry after the cooldown. Never infer a provider reason from acceptance.
6. Test backend rejection of a forced connection request while pending/failed or
   subscription-ineligible, even if browser controls are bypassed.
7. Confirm a campaign callback still updates its recipient and aggregate statistics.

## Remaining limitations

Previously discarded provider errors cannot be reconstructed. If Meta sends no
callback, status remains unconfirmed and polling eventually stops; manual refresh
is available. Missing callbacks require checking Meta and Render configuration/logs.
The existing architecture does not durably queue unknown message IDs: a callback
arriving before the initial send transaction commits can be ignored. Similarly,
a process failure between Meta acceptance and database commit is not made exactly
once by this change. A durable webhook inbox/outbox would be a separate reliability
change. No real delivery, production migration, deployment or environment change
has been performed.
