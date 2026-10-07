# Tenant WhatsApp connections on Render

Each organization owner connects their own WhatsApp Business account in Settings using Meta Embedded Signup. Organization IDs and individual sender tokens do not need to be entered in Render.

## Shared configuration: set once

Set these backend Render environment variables:

- `META_APP_ID`: your Meta App ID.
- `WHATSAPP_SIGNUP_CONFIG_ID`: Facebook Login for Business Embedded Signup Configuration ID.
- `META_APP_SECRET`: keep this private on the backend.
- `WHATSAPP_TOKEN_ENCRYPTION_KEY`: a stable Fernet key or a random secret of at least 32 characters. Keep it private and backed up. Changing it requires organizations to reconnect. The blueprint generates it for new services; configure it manually once for an existing service.
- `WHATSAPP_VERIFY_TOKEN`: your private webhook verification value.
- `WHATSAPP_PROVIDER=meta_cloud` and `WHATSAPP_GRAPH_VERSION=v23.0` (or a supported version configured for your app).

Configure the production frontend domain in Meta and a WhatsApp Embedded Signup configuration requesting `whatsapp_business_management` and `whatsapp_business_messaging`. Complete Meta's applicable business verification, app review, advanced access and live-mode requirements before onboarding other businesses. Code cannot grant those approvals.

Do not put secrets in frontend VITE variables. Local .env changes do not update Render. Legacy `WHATSAPP_ALLOWED_ORGANIZATION_IDS`, `WHATSAPP_PHONE_NUMBER_ID` and `WHATSAPP_ACCESS_TOKEN` are no longer used. Existing shared credentials are not automatically assigned to a tenant.

## Webhooks and database

Configure `https://crd-b.onrender.com/api/webhooks/whatsapp` in Meta, verify it with your verification token, and subscribe to the messages field. Connecting a tenant also subscribes this app to its authorized WABA. POST callbacks require a valid Meta signature and match both the sender and WABA to the tenant connection.

The release adds whatsapp_connections and whatsapp_signup_attempts tables. AUTO_CREATE_TABLES creates missing tables at startup. Deployments already managed by Alembic should run `alembic upgrade head` against a correctly stamped database. Do not stamp or migrate an unfamiliar production database blindly.

## Owner onboarding

1. Open Settings and choose Connect WhatsApp.
2. Choose Continue with Meta and authorize your business account.
3. Select a phone number from the assets verified by the backend with Meta.
4. If this is a new number needing API registration, select that option and enter its six-digit registration PIN.
5. Confirm the connection.

Only the organization owner can connect or disconnect. Signup attempts expire after ten minutes and are bound to the user, tenant and organization. The backend validates the token's app, permissions and authorized assets. Tokens are encrypted with tenant-bound data and never returned to the browser.

Every send resolves the signed-in organization's connection. Missing or expired connections are rejected; there is no shared sender fallback. Disconnect removes this CRM's stored credentials and stops its sends. It does not delete Meta assets or revoke permissions in Meta; the owner can revoke those separately in Meta.

## Delivery and limits

Meta accepting a message is not proof of delivery. A delivered or read webhook confirms delivery; failed includes the provider error. Free-form messages require an open customer service window; otherwise use an approved Meta template with its exact language and parameters. Test senders have recipient restrictions.

Immediate broadcasts process at most 20 recipients synchronously. Scheduling, large campaigns, automatic replies and local media uploads still require additional implementation. Public HTTPS media URLs are supported. Single sends do not have persistent broadcast-job delivery history. Historical placeholder success records are not delivery evidence and are not resent.

## Verification

Local unit/security tests and frontend build/lint validate the implementation. PostgreSQL integration tests cover signup, replay prevention, sender ownership, encrypted storage, tenant sends and signed callback isolation; run against a dedicated *_test database or GitHub CI. No real customer messages are sent by these tests. Live onboarding and phone delivery require the shared Render settings and Meta approvals above.
