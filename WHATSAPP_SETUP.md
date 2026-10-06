# WhatsApp on Render

Set these **backend** Render environment variables using the same Meta application
and sender that successfully sends from Meta's API testing screen:

- `WHATSAPP_PROVIDER=meta_cloud`
- `WHATSAPP_GRAPH_VERSION=v23.0` (or the supported version configured for your app)
- `WHATSAPP_PHONE_NUMBER_ID`: sender's **phone number ID**, not its phone number or WABA ID
- `WHATSAPP_ACCESS_TOKEN`: a valid token authorized to send for that sender
- `META_APP_SECRET`: Meta application's secret, used for webhook signature verification
- `WHATSAPP_VERIFY_TOKEN`: the verification token configured in Meta

Do not put these credentials in frontend `VITE_*` variables. Local `.env` changes
do not update Render environment variables.

In Meta, configure the callback URL as
`https://<your-backend>.onrender.com/api/webhooks/whatsapp`, verify it with the
configured verification token, and subscribe to the `messages` webhook field.
The GET endpoint verifies the callback; POST verifies Meta's signature and saves
delivery statuses and errors against the returned message IDs.

For the first application test, send to the **same recipient** that received the
Meta test. Indian 10-digit local numbers are prefixed with `91`; other countries
should use explicit international numbers. A Meta test sender may only send to
recipients registered and verified in its API testing screen.

Free-form text and quick replies require an open customer service window. Have
the intended recipient message the configured business number first, then send
your reply. To initiate a conversation outside that window, use an approved Meta
template with its exact name and language. The bulk composer accepts the name
and language for approved templates with no dynamic parameters; parameterized
templates can be sent through the API using a `template` object with `components`.
Saved CRM message text is not automatically an approved Meta template.

An API acceptance (`wamid` message ID) is **not** delivery. Inspect recipient
statuses and errors in the broadcast queue. `accepted` waits for a callback;
`delivered` or `read` confirms delivery; `failed` includes Meta's error code.
`unknown` means a timeout or invalid response left acceptance uncertain: check
delivery before retrying to avoid duplicate messages.

Immediate broadcasts currently process at most 20 recipients synchronously.
Large campaigns, automatic scheduling, and attachment uploads require a durable
worker and media implementation. They are rejected rather than silently marked
delivered. Existing historical records created by the old placeholder code are
not evidence of delivery and are not resent automatically.
