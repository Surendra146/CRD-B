# WhatsApp template workflow

Implemented in the existing FastAPI and React applications. Nothing was pushed or deployed, and no migration was applied to an application database.

## Local setup

From `D:\web apps\Python\CBD_Python`, with the **local development database** configured:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
# Use your existing migration/operator database role, not the runtime role.
# Confirm DATABASE_URL / migration configuration targets local development first.
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

The new revision is `f91c320ab010`, following `f91c320ab009`. It adds one non-null JSONB `workflow` column with an empty-object default to `whatsapp_templates`. Existing records, content and tenant RLS policies are retained. Legacy approved templates are read through an adapter; their approved definition is captured before their first draft edit. No new database role or policy is introduced. Coordinate application rollout with the migration; old databases without the column cannot run this code.

From `D:\web apps\React\CBD project`:

```powershell
npm.cmd run dev
```

## Storage and configuration

- Set `WHATSAPP_TEMPLATE_MEDIA_ROOT` to a private persistent directory. The default is `.template-media` relative to the backend working directory. Use an absolute path when API and workers have different working directories.
- All API replicas and campaign workers must share this directory. A local ephemeral filesystem is insufficient for scheduled campaigns. Back it up alongside the database. Keep it outside public/static directories and limit filesystem permissions to the service identity.
- Files use tenant/organization/template/UUID paths, original names are sanitized for display, and SHA-256 verifies retained bytes. File previews require the same authenticated organization/module access as the template. HTTP responses use private/no-store and nosniff headers.
- Install `ffprobe` and optionally set `WHATSAPP_FFPROBE` to its absolute executable path. MP4 uploads fail with a configuration error until codec validation is available. H.264 video with zero or one AAC audio track is supported. No transcoding is performed.
- `Pillow` verifies JPEG/PNG and `pypdf` parses unencrypted PDFs. JPEG/PNG headers are limited to 5 MB, MP4 to 16 MB, PDF to 100 MB. Images over 40 million pixels and animated images are additionally rejected by this application.
- Preserve the existing `META_APP_ID`, configured Graph API version (`v23.0` in this workspace), app secret, encrypted organization connection tokens and encryption key. No organization may use global fallback sending credentials.
- The submission sample goes through `/{app-id}/uploads` then `/{upload-id}` with `file_offset: 0`. Its returned `h` is used only in `example.header_handle`.
- Sending separately uploads private bytes to `/{phone-number-id}/media`; the returned numeric media ID is included in the template header parameter. Queue dispatch uploads again from the retained asset, so expired messaging IDs do not invalidate scheduled jobs. Missing/corrupt files require upload and selection of a new asset before creating a replacement campaign.
- Files are retained when removed from a draft because approved or queued versions may still reference them. There is no automatic retention/garbage-collection job in this change. Apply organizational retention policies to backups as well.

## Data and APIs

`content` is the local editable draft. Server-owned `workflow.submitted`, `workflow.approved`, and `workflow.approved_history` retain complete component definitions, component-specific recipient mappings/examples, WABA/sender identifiers, sample references and Meta identity. Approval state/rejection/sync timestamps are separate from draft revisions. The list displays both a pending/rejected new submission and the old approved sending version when applicable.

Draft shape (existing create/update routes):

```json
{
  "name": "Welcome",
  "category": "UTILITY",
  "content": {
    "meta_name": "welcome_customer",
    "sender_phone_number_id": "CONNECTED_PHONE_NUMBER_ID",
    "language": "en_US",
    "header": {"type": "IMAGE", "asset_id": "UPLOADED_ASSET_UUID"},
    "body": "Hi {{name}}, your order is ready.",
    "footer": "Thank you",
    "buttons": [{"type": "URL", "text": "Website", "url": "https://example.com"}],
    "mappings": {"body": {"name": "customer.name"}},
    "examples": {"body": {"name": "Alice"}}
  }
}
```

- `POST /api/templates/{id}/media`: authenticated multipart `file`, validates and stores a sample or sending asset.
- `GET /api/templates/{id}/media/{asset_id}`: authenticated file preview.
- `POST /api/templates/{id}/submit`: validate, upload sample if needed and submit to the connected WABA.
- `POST /api/templates/{id}/refresh`: retrieve approval/rejection and reconcile uncertain submissions.
- `POST /api/saas/templates/sync`: complete paginated WABA sync, preserving local drafts and mappings when the approved schema still matches. Merge primarily by scoped Meta ID; scoped submitted name/language reconciles lost submission responses. Missing templates are disabled after a complete snapshot.
- Existing module grants and viewer restrictions apply to mutations. Template routes permit the existing `templates` or `whatsapp` grants. Sending retains WhatsApp permissions, subscription checks, consent windows, scheduling/outbox and webhook delivery tracking.

Submission locks the organization for name reservation, commits an explicit in-progress snapshot before the provider creation call, and rejects concurrent clicks/retries. Definitive validation/permission failures preserve the draft and allow correction/retry. Network uncertainty requires refresh. If Meta still has no matching name/language after five minutes, refresh marks it retryable; an unchanged retry reuses the exact reserved name to avoid creating another Meta version. Submitted/approved records cannot be deleted locally while queued jobs may refer to them.

An edited approved template submits under an automatically generated `_rXXXXXXXX` name. It does not edit the approved provider definition in place. The old approved snapshot remains usable until another version is approved. Historical queued versions retain their original payloads and asset references; superseded versions are checked against Meta before dispatch.

Positional conversion numbers unique placeholders in first-appearance order independently for body, header and each URL button. Repeated placeholders reuse their position. Text headers support one distinct variable; dynamic website buttons support one suffix variable. Examples are only used for approval. Allowed recipient fields are name, phone, email, city, lifecycle.segment, lifecycle.totalSpent and demographics.city. Missing values fail before queuing. `city` resolves the explicit recipient city or demographics.city. External positional templates can supply component-to-field-list mappings when sending; unknown provider content cannot be replaced with arbitrary components.

Direct and bulk sending select an approved definition, with organization, approval and WABA validation even when consent enforcement is disabled:

```json
{
  "phone": "919000000000",
  "sender_phone_number_id": "CONNECTED_PHONE_NUMBER_ID",
  "template": {"id": 123, "media_asset_id": "UPLOADED_ASSET_UUID"},
  "recipient": {"name": "Alice"}
}
```

Bulk Sender and Campaigns expose approved compatible templates, connected account selection and shared campaign assets. Campaigns stores `audience.sender_phone_number_id`, `audience.template_media_asset_id` and `audience.template_mappings`; launch delegates to the same bulk validation and snapshot logic. Recipient-specific media is intentionally unavailable. Campaigns selects retained assets; use Templates or Bulk Sender to upload replacements.

## Manual verification

1. Connect an organization's sending account, then create a MARKETING/UTILITY draft with exact language and lowercase Meta name. Save, close and reopen it.
2. Add a text header, `Hi {{name}}, welcome.` body, footer and buttons. Map `name` to customer.name and provide an example. Verify repeated variables reuse one position; missing mappings/examples and invalid URLs/phones fail clearly.
3. Switch to image, MP4 or PDF header. Upload, preview, replace and remove sample selection. Test disguised extensions, false MIME types, size limits and a different organization's asset URL.
4. Submit once, then click again: only one submission should exist. Confirm the pending state in Meta WhatsApp Manager. Refresh to approved/rejected and inspect rejection details. If the network response is lost, refresh to reconcile before retrying.
5. Edit an approved draft, save it, and confirm the list still identifies the previous exact approved name/language. Submit the edit and confirm the new revision has a different Meta name.
6. In Bulk Sender, choose the sending account and its approved template. Confirm another WABA's templates and unsupported formats are absent. Select or upload a valid sending asset. External templates without the original sample should work after explicit recipient mappings and sending-media selection.
7. Send to two opted-in test recipients with different names. Check exact approved language/name, personalized header/body/URL parameters, approved static buttons and inline image/video/document. Verify no extra interactive message is sent.
8. Schedule a media campaign, then edit the local draft. Run the worker and verify the retained approved version and asset are used exactly once. Test a missing file and paused/disabled approval; the job must fail clearly without falling back to edited text.
9. Synchronize twice. Confirm no duplicate rows, intact local edits, matching approval states and updated last-sync times. Exercise viewer and other-organization access.
10. Confirm webhook delivery/read states update the queue independently of provider acceptance.

## Validation and remaining limits

Automated tests exercise conversion, exact payloads, file/MIME/codec validation, ownership, snapshots, submission retries, approval updates, API permissions, per-recipient sending, sync and worker media behavior. Final checks on October 17, 2026:

- Backend: `python -m pytest -q -p no:cacheprovider`: **309 passed, 34 skipped**, plus six subtests. One existing Starlette/httpx deprecation warning. The skipped disposable-RLS security cases require their separate sandbox runner; ordinary PostgreSQL/API tests do not replace those cases.
- Frontend: `npm.cmd test`: **27 passed**, followed by a successful Vite production build. Vite reported that the existing HMR port 24678 was occupied; tests/build still completed successfully.
- Targeted ESLint: Templates, BulkSenderTab, Campaigns, templates service, compatibility utility and its tests all passed.
- Alembic offline SQL: `alembic upgrade f91c320ab009:f91c320ab010 --sql` passed and emitted only the new column plus Alembic's version update. No migration was applied.
- `git diff --check` passed for changed backend sources, tests and migration files.

Standard MARKETING/UTILITY templates support text/image/video/PDF headers, body, footer, static/dynamic HTTPS URL buttons, one international Call Now button and grouped quick replies. The application supports up to ten buttons, at most two URLs and one phone button. Specialized authentication/OTP, location, carousel, flow, catalog/product, payments, copy-code, limited-time offers and provider named parameters are explicitly unsupported. Recipient-specific media, object-storage adapters, transcoding and automatic approval polling/webhook updates are not implemented; use Refresh or Synchronize. Meta remains authoritative for policy, category and account eligibility.

This implementation uses the configured Graph version instead of hard-coding a new version. Official references consulted:

- [Meta template components](https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/components)
- [Meta media reference](https://developers.facebook.com/documentation/business-messaging/whatsapp/business-phone-numbers/media)
- [Meta's official template creation example](https://www.postman.com/meta/whatsapp-business-platform/request/n3jhmr4/create-template-w-image-header-text-body-text-footer-and-2-call-to-action-buttons)
- [Meta's official resumable session example](https://www.postman.com/meta/whatsapp-business-platform/request/vkmioqf/resumable-upload-create-an-upload-session)
- [Meta's official file-data upload example](https://www.postman.com/meta/whatsapp-business-platform/request/jruartu/resumable-upload-upload-file-data)

The developer reference pages returned HTTP 429 during this session; official Postman examples were accessible. Complete current-version limit/eligibility verification and a real test-WABA submission/send remain manual verification requirements. No real template was submitted and no recipient was messaged by this implementation session.

## Changed files

Backend: `app/models/whatsapp_template.py`, `app/routers/templates.py`, `app/routers/communications.py`, `app/routers/campaigns.py`, `app/routers/managed_whatsapp.py`, `app/services/consent.py`, new `app/services/template_definitions.py`, `template_media.py`, `template_workflow.py`, Alembic revision `f91c320ab010_template_workflow.py`, `requirements.txt`, `.env.enterprise.example`, `.gitignore`, this document, new unit/API lifecycle tests and adapted legacy campaign/WhatsApp regression fixtures.

Frontend: `src/Pages/CLC/Templates.jsx`, `src/Pages/CLC/whatsapp/BulkSenderTab.jsx`, `src/Pages/CLC/Campaigns.jsx`, `src/services/templates.js`, new `src/utils/metaTemplates.js` and `tests/metaTemplates.test.js`.
