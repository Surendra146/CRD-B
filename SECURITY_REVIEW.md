# Project review — 6 October 2026

The review covered backend routes, shared update helpers, authentication,
organization permissions, Meta sending, webhook handling, frontend messaging
flows, dependency advisories, and the deployed webhook endpoint. This is a
code review and regression check, not a penetration test or security guarantee.

## Implemented corrections

- Customer, template, campaign, segment, and auto-reply updates cannot overwrite
  record IDs, tenant or organization ownership, or creation metadata.
- Member and role management require the actual organization owner. Member
  creation requires an explicit password and cannot grant ownership.
- Inactive accounts cannot log in. Tokens require expiration, carry an issuance
  timestamp, and become invalid after password changes. Cookie-authenticated
  writes require an allowed Origin.
- Module access is enforced by the backend, rather than only in the sidebar.
- Production Meta sends require a tenant connection and WhatsApp permission.
  New organizations cannot automatically use another business's configured sender.
- Authentication attempts are rate-limited per client and application worker;
  request bodies are bounded to 10 MiB, with a 1 MiB webhook limit.
- Production disables the legacy unauthenticated socket progress endpoint. The
  authenticated HTTP upload-status endpoints remain available.
- Meta bearer credentials stay on the backend and are never forwarded through
  redirects. Phone-number ID and Graph version are validated before requests.
- Text, approved templates, quick replies, and a single public HTTPS media URL
  use real Meta Cloud API requests. Local uploads and unsupported combinations
  fail explicitly. Broadcast requests honor their configured dispatch interval.
- Signed webhooks record confirmed statuses; malformed data and invalid
  timestamps no longer crash status handling.
- The directory lookup returns only actual OpenStreetMap records and explicitly
  identifies its source. It never generates phone numbers, websites, ratings,
  or additional leads when the provider returns fewer results.
- Phone-number filtering reports format validation only, not WhatsApp registration.
- Unimplemented OTP verification, password reset delivery, campaign automation,
  and campaign resumption no longer return misleading successful results.
- Compatible frontend dependency updates removed 33 audit findings. PyJWT was
  updated to 2.15.1 locally, with a >=2.15 production requirement.

## Validation

- 43 local backend unit and security regression tests passed.
- Full frontend production build and lint passed after dependency updates.
- npm audit and pip-audit reported no known vulnerabilities after the updates.
- PostgreSQL integration regression tests were added for immutable ownership,
  member privilege escalation, inactive login, dispatch, and signed delivery.
  Local integration execution still requires a dedicated database ending in
  `_test`; the application's database must not be used for tests.
- The deployed backend exposed both GET and POST webhook routes and rejected
  an unsigned POST with HTTP 403. This confirms a live app secret is configured,
  but not that it matches Meta's secret.
- A real read-only Meta sender probe was prepared but could not run: the local
  environment has no configured Meta phone-number ID/access token. Render's
  private environment is not accessible through this workspace.
- No real customer messages were sent as part of the review.
- Neither repository tracks `.env`. An exact-value scan found no configured
  local secrets in tracked files or the frontend production bundle after removing
  the hardcoded database credential fallback. This does not scan all Git history
  or establish that credentials have never been exposed.

## Tenant connection configuration

The manual organization allowlist and global sender have been replaced by owner-managed Meta Embedded Signup. Configure META_APP_ID, WHATSAPP_SIGNUP_CONFIG_ID, META_APP_SECRET and a stable WHATSAPP_TOKEN_ENCRYPTION_KEY once in Render. Each owner connects their own account in Settings. Credentials are encrypted and tenant-bound; sends and signed delivery callbacks resolve the relevant organization connection. See WHATSAPP_SETUP.md for prerequisites and limitations. Live onboarding remains dependent on Meta approvals and actual deployment configuration.

## Features and remaining limits

| Feature | Actual behavior |
| --- | --- |
| Immediate WhatsApp broadcast | Real Meta requests; at most 20 recipients |
| Public media URL | One HTTPS image, video, or document per request |
| Approved template sending | Real Meta template name/language/components |
| Saved CRM templates | Local records; not automatic Meta registration/approval |
| Delivery status | Verified Meta webhook statuses for broadcast jobs |
| Auto-reply rules | Saved rules and a local tester; inbound replies not connected |
| Scheduling/campaign automation | Explicitly unavailable; durable worker needed |
| Group tools | Parse supplied text and invite-link formats; no live joins or membership lookup |
| Directory search | Real OpenStreetMap records; not Google Places |
| Number filtering | Formatting and deduplication; no registration lookup |
| OTP/password reset | Unavailable until real verified provider flows are implemented |

Broadcast processing is synchronous. Request interruptions can leave uncertain
or queued entries; check delivery before retrying. A durable worker, idempotency
keys, and an inbox for callbacks arriving before message IDs are committed are
needed for reliable large-scale operation. Single sends use Meta but do not have
persistent broadcast-job delivery history. Auth throttling is per worker; a shared
Redis or gateway policy is needed across multiple replicas. Bearer tokens remain
in browser storage, so XSS prevention and a future cookie-only session migration
remain relevant. Historical fabricated lead records and old placeholder delivery
logs were not deleted or rewritten automatically.

Known-advisory scans do not establish that a project is completely secure.
Production credential scopes, token expiry, business approval, backup retention,
hosting access, and actual phone delivery still require operational verification.
