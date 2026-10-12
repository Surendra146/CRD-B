# Frontend/backend API integration review

Reviewed on 11 October 2026. Backend: `D:\web apps\Python\CBD_Python`. Frontend: `D:\web apps\React\CBD project`.

## Result and scope

The final source inventory contains **142 backend HTTP operations and 125 frontend service request definitions**. All 125 request definitions resolve to a backend path with the correct HTTP method. Of these, 104 have references in UI/store/hook code and 21 are unused or compatibility operations. No duplicate backend method/path registrations or collection URL slash redirects remain in the audited frontend services.

This was a source and test review of the frontend API services and their consumers, backend route registration, request schemas, response construction, models/serialization, tenant/module permissions, authentication, upload processing, CORS, Socket.IO progress, environment configuration, Render blueprints, and existing test/CI setup. The endpoint inventory is exhaustive for the current service definitions. Payload/response verification combines code inspection and regression/API tests; it is not a claim that every business workflow was exercised interactively in a browser or in production.

**Production remains unhealthy:** the deployed backend `/ready` returned **503 on two checks**, while `/health` returned 200. Production routes, the frontend API origin, CORS, and unauthenticated access were checked successfully. Authenticated production CRUD, subscriptions, live Meta delivery, and worker execution were not exercised. The local fixes have not been deployed by this review.

Artifacts:

- `API_ENDPOINT_INVENTORY.json`: every frontend service request, its source location, matching backend routes, UI reference classification, uncovered backend operations, and duplicate registration results.
- `RENDER_API_VERIFICATION.json`: the read-only production HTTP check results.
- `FRONTEND_API_FIXES.patch`: consolidated frontend changes, including newly added helper and regression test files.
- `scripts/audit_api_connections.py`: repeatable cross-repository route inventory, without entering application lifespan or connecting to an application database.

## Issues found and fixes applied

| Issue | Impact before the fix | Change |
|---|---|---|
| Ten frontend collection calls omitted backend trailing slashes | Redirects on customer, campaign, segment, template, notification and upload requests; an extra proxy-dependent hop | Use canonical collection URLs ending in `/` |
| Backend origins ending in `/api` or extra slashes | Service URLs already contain `/api`, causing `/api/api/...` | Shared origin resolver trims whitespace/slashes and normalizes the legacy `/api` suffix |
| Missing or localhost backend setting on Render | A static SPA can serve HTML for API requests or point deployed browsers at their own localhost | Render builds validate a public HTTPS backend origin; same-origin proxy behavior remains available outside Render |
| Five removed custom dashboard endpoints remained in an unused service | Accidental use generated calls to nonexistent routes | Retain the service exports for import compatibility, but reject explicitly without issuing obsolete HTTP requests |
| Profile refresh expected `response.user`, whereas `/me` returns `data` | Refresh cleared the user's visible identity | Accept the backend `data` envelope and the existing `user` alias |
| Profile refresh logged out on every failure | Temporary network/503 failures destroyed local sessions | Only authentication failure triggers logout |
| Logout only cleared frontend storage | The backend HTTP-only cookie remained usable on the same origin | Call backend logout before clearing local state; sidebar/settings await completion; cookie clearing works even with an expired token |
| Axios could inherit an obsolete default Authorization header | Requests could retain credentials after storage was cleared | Remove the inherited bearer header when no stored token exists; clear defaults on 401 |
| FastAPI validation errors are arrays and authorization errors use `detail` | Users saw generic messages or non-string error values | Shared readable formatter handles string details, provider messages, validation arrays and network errors; affected page catches use it |
| Retry headers were not exposed to cross-origin JavaScript | Login rate-limit UI could not read `Retry-After` | Expose `Retry-After` and `Content-Disposition` through CORS |
| Notification queries ran for users without that module | Repeated avoidable 403 responses from page headers | Enable the request and notification button only when permission is present |
| WhatsApp requested customer/segment data without checking those permissions | WhatsApp-only users made forbidden dependent requests | Gate those queries using their matching customer/segment/campaign grants |
| Campaign-only users requested protected templates; viewer controls allowed mutations | Avoidable forbidden requests/actions | Gate template loading and campaign mutation controls using current grants/role |
| Segment import endpoints were placeholders | Template downloads were JSON, validation ignored files, save ignored payloads | Generate real XLSX templates; parse CSV/XLSX; validate customer/active-segment codes; return the UI's summary; save tenant-scoped mappings; generate error workbooks |
| Browser-supplied segment validation results were unchecked | A future implementation could trust forged or stale rows | Revalidate mappings on save; reject foreign, ambiguous, missing or duplicate codes; cap a request at 5,000 mappings |
| Upload report options and response shape did not match the page | User/type selectors were empty and report count read as zero | Return scoped users and upload types; implement date/user/type/limit filters; return `data.total` and `data.rows` |
| Report Excel/PDF and upload-error endpoints returned JSON | Files downloaded with spreadsheet/PDF extensions were invalid | Return actual XLSX/PDF bytes and correct MIME/disposition headers; error exports include staged invalid rows |
| Blank spreadsheet headers shifted subsequent column values; CSV headers with spaces lost values | A later named column read the wrong cell or values became empty | Retain physical column indices and normalize CSV header whitespace |
| Unknown/malformed upload files and types were accepted or raised generic errors | Empty misleading uploads or server errors | Reject unsupported import types/formats and return readable 400 errors for unreadable files |
| Frontend advertised 20 MB files but request middleware allows 10 MB including multipart overhead | Accepted files failed with 413 | Set the import UI limit to 9 MB; segment file selection advertises supported CSV/XLSX formats |
| Customer sort options use camelCase/JSON paths | Most sort choices silently fell back to date added | Map the supplied fields; sort numeric spending/order totals numerically |
| Customer sales updates replaced purchases without recomputing metrics | Customer totals and analytics could become stale | Recompute purchase metrics after purchase-array updates; validate/parse customer date updates |
| Campaign form sent `startDate`/`sendTime`, but launch reads `scheduledAt` | Scheduled campaigns could launch immediately | Send a future ISO `scheduledAt` using the displayed Kolkata timezone; validate schedules; normalize legacy date/time payloads too |
| Numeric saved-segment campaign filters were ignored | Reach estimates and recipients could be broader than configured | Apply the same day/spending/order filters to estimation and launch selection |
| Applying a saved WhatsApp template only copied body text | Sends lacked its approved template name/language | Populate Meta template identity/language from the selected record |
| Frontend broadcast limit was fixed at 20, while Render config allows a different limit | Valid production-sized custom broadcasts were blocked | Connect the existing configuration endpoint, expose/use the backend limit with a conservative fallback |
| Bulk preview only loads 200 customers, while the server can select all | A broadcast could include people absent from its displayed preview | Block non-custom broadcasts when the preview is incomplete and direct users to exact Custom Numbers |
| WhatsApp offer preview read `avgOrderValue`, while customer metrics use `averageOrderValue` | The preview used the fallback amount | Read the serialized customer metric name |
| Local Socket.IO accepted anonymous subscriptions to any upload ID | Unauthorized access to import progress/raw preview data | Authenticate socket connections and recheck upload module permission and tenant/organization ownership on subscription; production still uses authenticated HTTP polling |
| Readiness failures did not identify the failing dependency in application logs | `/ready` 503 was hard to diagnose | Log only the failed component and exception class; keep credentials and connection strings out of logs and the public response |
| Backend Blueprint did not explicitly request the frontend CORS origin | A newly configured service could retain localhost defaults | Add a manually supplied `CORS_ORIGINS` entry for the backend web service |

Binary PDF generation adds `reportlab>=4.4,<5` to backend dependencies. The changes do not require a database schema migration. Existing unrelated working-tree changes and both projects' `.env` files were preserved.

## Request and response contracts

The shared Axios response interceptor returns `response.data`. A normal service result is therefore the backend envelope itself, usually `{success, data}`, rather than an Axios response containing another `data` level. Paginated customer/campaign/bulk-job lists also return top-level `pagination`. Binary methods return the Blob body, with `responseType: 'blob'`.

The frontend uses JSON for mutations and `FormData` for upload validation/staging; Axios supplies the multipart boundary. Customer, campaign, template and segment payloads use camelCase aliases where the schemas declare them. SaaS/platform/onboarding payloads use the strict snake_case fields required by their backend models. Existing `PUT`/`PATCH` distinctions were preserved.

Segment mapping now uses `customerCode` (the customer's `externalId`) and `segmentCode` (an active segment's `code`). Successful validation returns `data.totalRows`, `validCount`, `errorCount`, `validRows`, and `errors`; successful save returns `data.savedRows`, `failedRows`, and `totalRows`. Save validates against the requesting organization's current records.

Report generation and both export types share the same filtering implementation. Dates select an inclusive calendar range, limited to 92 days; results remain bounded to 5,000 rows. The report's total may exceed the returned/exported limit. Upload-history responses retain their original list envelope and now honor the requested limit.

## Authentication, authorization and security findings

Bearer authentication is correctly attached to the shared client. Backend identity validation checks expiry, active user and tenant, tenant claim correspondence, organization ownership, password-change invalidation and database authorization context. Tenant/module restrictions and read-only viewer enforcement are server-side; frontend route/button guards are convenience checks, not the security boundary.

Cookie-authenticated mutations require an allowed Origin. Production login cookies remain HTTP-only/Secure/SameSite=Lax. Cross-origin React requests use the bearer token, so they do not depend on third-party cookie acceptance. Logout clears the cookie but does not revoke an already copied JWT; it remains valid until expiry or password invalidation, as in the existing session design. No server-side JWT denylist was introduced.

Production socket progress remains disabled; HTTP upload polling is connected. Local socket progress now applies identity/module/ownership checks. Backend Meta tokens remain encrypted/server-owned. Existing webhook signature checks, staff-only platform permissions, subscription requirements, consent checks and FORCE RLS restrictions were retained and tested.

Some viewer/limited-role screens still show controls that the backend rejects with 403. This is a remaining UI polish opportunity, rather than an authorization bypass. Under production RLS, report user options only include users visible to the caller's database authorization context; owner/admin and limited staff visibility should be included in deployed acceptance testing.

## Local and Render verification

| Check | Result |
|---|---|
| Local running backend `http://localhost:8000/health` | 200 JSON |
| Local frontend port at time of probe | No server listening; production compilation and existing Vite-backed page tests passed |
| Final full backend pytest suite | 242 passed, 26 skipped, 6 subtests passed |
| Additional final readiness/API contract run | 8 passed, including sanitized readiness diagnostics |
| Disposable PostgreSQL authorization suite | All 26 passed using actual restricted runtime/control logins and FORCE RLS |
| Authorization operator/key installation checks | Passed in the disposable cluster; existing databases were not used for these checks |
| Frontend tests | 17 passed |
| Frontend production build | Passed |
| Frontend ESLint | Passed |
| Final frontend/backend inventory | 125 request definitions matched; 0 unmatched; 0 duplicate backend operations; 0 slash redirects |
| Deployed frontend `https://crd-f.onrender.com/` | 200 HTML; bundle contains `https://crd-b.onrender.com` as the configured backend |
| Deployed backend `/health` | 200, `{success:true,status:"ok"}` |
| Deployed backend `/ready` | **503**, `{success:false,status:"unavailable"}`, repeated |
| Deployed OpenAPI | All 142 local backend method/path operations exist |
| Login preflight from the deployed frontend origin | 200 with exact allowed origin and credentials |
| Login preflight from an unrelated origin | 400 with no allowed-origin header |
| Deployed `/api/auth/me` without authentication | 401 |
| Deployed CORS exposed headers | New Retry-After/disposition exposure is not deployed yet |

The skipped pytest cases are the separate authorization suite; they passed through the dedicated sandbox runner. The test suite uses a dedicated `_test` PostgreSQL database and isolated schemas. The full ordinary suite runs with its existing test configuration; the separate sandbox is what verifies the restricted production-style roles. No production account was created, no production message was sent, and no live production data was changed.

## Remaining integrations and deployment work

1. **Resolve Render readiness before declaring production operational.** At least one of runtime PostgreSQL, control PostgreSQL or Redis is unavailable. The public response cannot distinguish them. Obtain Render logs/configuration, validate both database URLs and Redis connectivity, and run the existing authorization preflight as documented in `RENDER_AUTHORIZATION_PREFLIGHT.md`. The new diagnostics identify `runtime_database`, `control_database`, or `redis` after deployment. This review has no Render account access and did not change live secrets, resources or deployments.
2. Deploy both source changes, including the new frontend helper/tests and backend export/socket helper modules. Render's existing backend build installs `requirements.txt`, which now includes ReportLab. No new database migration is required for these changes.
3. On the Render frontend set `VITE_BACKEND_URL=https://crd-b.onrender.com`. The legacy `VITE_API_URL` may be omitted or kept consistent; the backend variable takes precedence. On the backend set `CORS_ORIGINS=https://crd-f.onrender.com`, adding actual custom frontend origins if used. Keep production socket progress disabled. The currently deployed origin and CORS are already correct; preserve them when deploying.
4. Rebuild the frontend when changing its API environment variables. Vite's values are compiled into the static assets, so a backend-only restart does not change the browser configuration. See [Render environment variable configuration](https://render.com/docs/configure-environment-variables) and [Render static-site deployment](https://render.com/docs/your-first-deploy).
5. After `/ready` becomes 200 and both deployments are updated, exercise authenticated login/logout, customer create/update, segment validation/save, reports/downloads, subscription visibility and queued sending using a designated test account. Live messaging additionally requires a valid paid subscription, encrypted connected Meta number, appropriate consent/approved template, signed webhook delivery and running Redis/Celery worker/beat. Code and simulated API tests cannot certify those external dependencies.
6. Password-reset and phone-OTP routes intentionally return 501 until verified provider/token flows exist. There is no working reset/OTP UI integration to enable safely without those implementations. Do not interpret route existence as completed functionality.
7. Cohorts, score recalculation, legacy dashboard analytics and notifications still have placeholder business behavior. The cohort/recalculation/legacy services have no current UI caller; notifications is connected but returns an empty list. Implement their actual data logic if those features are required.
8. Custom dashboard management has been removed from the product. Compatibility exports now fail explicitly and issue no missing-endpoint requests. Legacy Excel/custom-dashboard service methods remain unused; their processing/analytics is not a completed custom-dashboard feature. Preserve or remove these exports according to the product roadmap.
9. Auto-responder rules are persisted and their simulator is connected, but automated inbound replies are not implemented. Number filtering validates formatting, not whether a number has WhatsApp. Group tools parse supplied links/text; they do not automatically join groups or retrieve members from Meta. These limitations are also exposed by the backend configuration endpoint and require additional supported provider workflows if needed.
10. The 200-customer bulk preview is now guarded against sending to an unseen larger audience. Custom Numbers supports the configured backend broadcast limit. A complete paginated/server-driven audience preview is a future enhancement for large organizations.

## Duplicate, unused and unconnected operations

There are no duplicate registered method/path operations. `campaignsApi.start`/`launch`, `authApi.updateMemberRole`/`updateMemberAccess`, the two communications WhatsApp send paths and generic communications send are intentional compatibility aliases. They were preserved.

The final inventory identifies 21 service request definitions with no direct UI/store/hook reference. These include cohort/recalculation/legacy analytics, the older member-role alias, campaign detail/update/delete/start, customer deletion, seven Excel methods, lead history, SaaS message history, platform plan listing and template detail. Keeping a service export does not mean a corresponding screen is required. Their exact names and routes appear in the inventory appendix.

Backend-only operations fall into distinct groups:

- Infrastructure/provider: `/health`, `/ready`, and GET/POST `/api/webhooks/whatsapp` appropriately do not have React services.
- Compatibility/metadata: alternate communications send paths, `/api/fields`, `/api/system-fields`, and legacy analytics raw data have no current UI requirement.
- Optional account/customer features: auth token refresh, profile/password editing, customer purchase append and bulk-status update have backend routes but no current dedicated frontend controls. Add them if the product requires those actions; sales editing currently updates the existing purchase array through customer update.
- Platform usage reconciliation: POST `/api/platform/usage` is staff-only and has no console input form. Billing can display reconciled usage, but entry requires an authorized integration/operator flow.
- Unimplemented authentication flows: forgot/reset password endpoints are present but intentionally reject with 501.

Most backend handlers return dictionaries without explicit response models. The current consumers match the inspected envelopes, but introducing typed response contracts and a cross-repository CI contract check would reduce future drift. The inventory's `used_by_ui` field is a static reference classification, not proof that a user has exercised every branch.

To regenerate coverage, run from the backend:

```powershell
.\.venv\Scripts\python.exe -B scripts/audit_api_connections.py --frontend 'D:\web apps\React\CBD project'
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider
.\.venv\Scripts\python.exe -B scripts/run_authorization_sandbox.py
```

From the frontend, run `npm.cmd test` and `npm.cmd run lint`.

## Endpoint inventory appendix

`{value}` denotes a service argument substituted into a path. UI usage is a source-reference check.

| Service | Method | Request path | UI reference |
|---|---|---|---|
| `analyticsApi.getDashboard` | GET | `/api/analytics/dashboard` | Yes |
| `analyticsApi.getSegments` | GET | `/api/analytics/segments` | Yes |
| `analyticsApi.getCohorts` | GET | `/api/analytics/cohorts` | No |
| `analyticsApi.getChurn` | GET | `/api/analytics/churn` | Yes |
| `analyticsApi.getRevenue` | GET | `/api/analytics/revenue` | Yes |
| `analyticsApi.recalculateScores` | POST | `/api/analytics/recalculate` | No |
| `customDashboardAnalyticsApi.getFilters` | GET | `/api/analytics/{value}/filters` | No |
| `customDashboardAnalyticsApi.getData` | GET | `/api/analytics/{value}` | No |
| `authApi.logout` | POST | `/api/auth/logout` | Yes |
| `authApi.login` | POST | `/api/auth/login` | Yes |
| `authApi.register` | POST | `/api/auth/register` | Yes |
| `authApi.verifyPhoneOtp` | POST | `/api/auth/verify-phone-otp` | Yes |
| `authApi.getMe` | GET | `/api/auth/me` | Yes |
| `authApi.getOrganizationSettings` | GET | `/api/auth/organization-settings` | Yes |
| `authApi.updateOrganizationSettings` | PATCH | `/api/auth/organization-settings` | Yes |
| `authApi.getMembers` | GET | `/api/auth/members` | Yes |
| `authApi.createMember` | POST | `/api/auth/members` | Yes |
| `authApi.updateMember` | PATCH | `/api/auth/members/{value}` | Yes |
| `authApi.updateMemberRole` | PATCH | `/api/auth/members/{value}/role` | No |
| `authApi.updateMemberAccess` | PATCH | `/api/auth/members/{value}/role` | Yes |
| `authApi.getRoles` | GET | `/api/auth/roles` | Yes |
| `authApi.createRole` | POST | `/api/auth/roles` | Yes |
| `authApi.updateRole` | PATCH | `/api/auth/roles/{value}` | Yes |
| `campaignsApi.getAll` | GET | `/api/campaigns/` | Yes |
| `campaignsApi.getById` | GET | `/api/campaigns/{value}` | No |
| `campaignsApi.create` | POST | `/api/campaigns/` | Yes |
| `campaignsApi.update` | PUT | `/api/campaigns/{value}` | No |
| `campaignsApi.delete` | DELETE | `/api/campaigns/{value}` | No |
| `campaignsApi.launch` | POST | `/api/campaigns/{value}/launch` | Yes |
| `campaignsApi.start` | POST | `/api/campaigns/{value}/launch` | No |
| `campaignsApi.pause` | POST | `/api/campaigns/{value}/pause` | Yes |
| `campaignsApi.resume` | POST | `/api/campaigns/{value}/resume` | Yes |
| `campaignsApi.complete` | POST | `/api/campaigns/{value}/complete` | Yes |
| `communicationsApi.configuration` | GET | `/api/communications/whatsapp/configuration` | Yes |
| `communicationsApi.sendWhatsApp` | POST | `/api/communications/whatsapp/send` | Yes |
| `communicationsApi.sendBulkWhatsApp` | POST | `/api/communications/whatsapp/bulk` | Yes |
| `communicationsApi.getBulkJobs` | GET | `/api/communications/whatsapp/bulk` | Yes |
| `communicationsApi.getBulkJob` | GET | `/api/communications/whatsapp/bulk/{value}` | Yes |
| `communicationsApi.bulkJobAction` | POST | `/api/communications/whatsapp/bulk/{value}/action` | Yes |
| `customersApi.getAll` | GET | `/api/customers/` | Yes |
| `customersApi.getById` | GET | `/api/customers/{value}` | Yes |
| `customersApi.create` | POST | `/api/customers/` | Yes |
| `customersApi.update` | PUT | `/api/customers/{value}` | Yes |
| `customersApi.delete` | DELETE | `/api/customers/{value}` | No |
| `customersApi.getTimeline` | GET | `/api/customers/{value}/timeline` | Yes |
| `customersApi.addInteraction` | POST | `/api/customers/{value}/interactions` | Yes |
| `excelApi.upload` | POST | `/api/excel/upload` | No |
| `excelApi.getByDashboardId` | GET | `/api/excel/{value}` | No |
| `excelApi.mapColumns` | POST | `/api/excel/map-columns` | No |
| `excelApi.processUpload` | POST | `/api/excel/{value}/process` | No |
| `excelApi.getStatus` | GET | `/api/excel/{value}/status` | No |
| `excelApi.getUploadJobStatus` | GET | `/api/excel/upload-jobs/{value}/status` | No |
| `excelApi.getHistory` | GET | `/api/excel/history` | No |
| `marketingToolsApi.filterNumbers` | POST | `/api/marketing/filter-numbers` | Yes |
| `marketingToolsApi.searchGMaps` | POST | `/api/marketing/gmaps-extractor/search` | Yes |
| `marketingToolsApi.importGMapsLeads` | POST | `/api/marketing/gmaps-extractor/import` | Yes |
| `marketingToolsApi.getGMapsHistory` | GET | `/api/marketing/gmaps-extractor/history` | No |
| `marketingToolsApi.getAutoResponderRules` | GET | `/api/marketing/auto-responder` | Yes |
| `marketingToolsApi.createAutoResponderRule` | POST | `/api/marketing/auto-responder` | Yes |
| `marketingToolsApi.updateAutoResponderRule` | PUT | `/api/marketing/auto-responder/{value}` | Yes |
| `marketingToolsApi.deleteAutoResponderRule` | DELETE | `/api/marketing/auto-responder/{value}` | Yes |
| `marketingToolsApi.testAutoResponder` | POST | `/api/marketing/auto-responder/test` | Yes |
| `marketingToolsApi.parseGroupLinks` | POST | `/api/marketing/group-tools/parse-links` | Yes |
| `marketingToolsApi.grabGroupMembers` | POST | `/api/marketing/group-tools/grab-members` | Yes |
| `marketingToolsApi.importGroupMembers` | POST | `/api/marketing/group-tools/import-members` | Yes |
| `notificationsApi.getAll` | GET | `/api/notifications/` | Yes |
| `saasApi.profile` | GET | `/api/saas/profile` | Yes |
| `saasApi.updateProfile` | PUT | `/api/saas/profile` | Yes |
| `saasApi.plans` | GET | `/api/saas/plans` | Yes |
| `saasApi.subscription` | GET | `/api/saas/subscription` | Yes |
| `saasApi.invoices` | GET | `/api/saas/invoices` | Yes |
| `saasApi.usage` | GET | `/api/saas/usage` | Yes |
| `saasApi.onboarding` | GET | `/api/saas/onboarding` | Yes |
| `saasApi.requestOnboarding` | POST | `/api/saas/onboarding` | Yes |
| `saasApi.numbers` | GET | `/api/saas/numbers` | Yes |
| `saasApi.defaultNumber` | POST | `/api/saas/numbers/{value}/default` | Yes |
| `saasApi.disconnectNumber` | DELETE | `/api/saas/numbers/{value}` | Yes |
| `saasApi.syncTemplates` | POST | `/api/saas/templates/sync` | Yes |
| `saasApi.consents` | GET | `/api/saas/consents` | Yes |
| `saasApi.setConsent` | POST | `/api/saas/consents` | Yes |
| `saasApi.messages` | GET | `/api/saas/messages` | No |
| `platformApi.subscriptions` | GET | `/api/platform/subscriptions` | Yes |
| `platformApi.organizations` | GET | `/api/platform/organizations` | Yes |
| `platformApi.subscriptionPlans` | GET | `/api/platform/subscription-plans` | Yes |
| `platformApi.manageSubscription` | POST | `/api/platform/tenants/{value}/organizations/{value}/subscription/{value}` | Yes |
| `platformApi.access` | GET | `/api/platform/access` | Yes |
| `platformApi.overview` | GET | `/api/platform/overview` | Yes |
| `platformApi.tenants` | GET | `/api/platform/tenants` | Yes |
| `platformApi.setTenant` | PATCH | `/api/platform/tenants/{value}` | Yes |
| `platformApi.plans` | GET | `/api/platform/plans` | No |
| `platformApi.createPlan` | POST | `/api/platform/plans` | Yes |
| `platformApi.onboarding` | GET | `/api/platform/onboarding` | Yes |
| `platformApi.updateOnboarding` | PATCH | `/api/platform/onboarding/{value}` | Yes |
| `platformApi.audit` | GET | `/api/platform/audit` | Yes |
| `segmentsApi.getAll` | GET | `/api/segments/` | Yes |
| `segmentsApi.create` | POST | `/api/segments/` | Yes |
| `segmentsApi.update` | PUT | `/api/segments/{value}` | Yes |
| `segmentsApi.delete` | DELETE | `/api/segments/{value}` | Yes |
| `segmentsApi.downloadImportTemplate` | GET | `/api/segments/import/template` | Yes |
| `segmentsApi.validateImportFile` | POST | `/api/segments/import/validate` | Yes |
| `segmentsApi.saveValidatedRows` | POST | `/api/segments/import/save` | Yes |
| `segmentsApi.exportImportErrors` | POST | `/api/segments/import/export-errors` | Yes |
| `templatesApi.getAll` | GET | `/api/templates/` | Yes |
| `templatesApi.getById` | GET | `/api/templates/{value}` | No |
| `templatesApi.create` | POST | `/api/templates/` | Yes |
| `templatesApi.update` | PUT | `/api/templates/{value}` | Yes |
| `templatesApi.delete` | DELETE | `/api/templates/{value}` | Yes |
| `uploadsApi.upload` | POST | `/api/uploads/` | Yes |
| `uploadsApi.suggestMappings` | POST | `/api/uploads/suggest-mappings` | Yes |
| `uploadsApi.getTargetFields` | GET | `/api/uploads/target-fields` | Yes |
| `uploadsApi.setMapping` | PUT | `/api/uploads/{value}/mapping` | Yes |
| `uploadsApi.process` | POST | `/api/uploads/{value}/process` | Yes |
| `uploadsApi.confirmSave` | POST | `/api/uploads/{value}/confirm-save` | Yes |
| `uploadsApi.getStatus` | GET | `/api/uploads/{value}/status` | Yes |
| `uploadsApi.getHistory` | GET | `/api/uploads/history` | Yes |
| `uploadsApi.getRecentUploadReport` | GET | `/api/uploads/history/report` | Yes |
| `uploadsApi.getRecentUploadReportOptions` | GET | `/api/uploads/history/report/options` | Yes |
| `uploadsApi.exportRecentUploadReportExcel` | GET | `/api/uploads/history/report/export/excel` | Yes |
| `uploadsApi.exportRecentUploadReportPdf` | GET | `/api/uploads/history/report/export/pdf` | Yes |
| `uploadsApi.exportErrors` | GET | `/api/uploads/{value}/errors/export` | Yes |
| `whatsappConnectionApi.status` | GET | `/api/whatsapp-connection/` | Yes |
| `whatsappConnectionApi.start` | POST | `/api/whatsapp-connection/start` | Yes |
| `whatsappConnectionApi.exchange` | POST | `/api/whatsapp-connection/exchange` | Yes |
| `whatsappConnectionApi.select` | POST | `/api/whatsapp-connection/select` | Yes |
| `whatsappConnectionApi.disconnect` | DELETE | `/api/whatsapp-connection/` | Yes |
