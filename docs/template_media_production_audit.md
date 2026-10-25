# Production template media audit: access blocked

The repository does not establish whether production contains media. No production connection or tenant-data query was performed during this task. Counts and migration necessity remain unknown, not zero.

## Inspected reference locations

- `app/models/whatsapp_template.py`: `public.whatsapp_templates`, scoped by tenant and organization, contains JSONB `workflow`.
- `workflow.assets[]`: binary metadata with `id`, `type`, `mime`, `size`, `name`, `sha256`. Keys are derived as `{tenant_id}/{organization_id}/{template_id}/{asset_id}`; the database does not track a per-asset storage backend.
- `content.header.asset_id`: current draft media selection.
- `workflow.submitted.sample_asset_id`, `workflow.approved.sample_asset_id` and `workflow.approved_history[].sample_asset_id`: compiled template approval references. Historical entries must be retained. Provider sample handles and Meta messaging IDs are not local file keys.
- `app/models/whatsapp_marketing.py`: `public.whatsapp_bulk_jobs.audience_payload.template_snapshot` contains `template_id`, `asset_id`, `definition`, and `mappings`. The definition can also contain `sample_asset_id`. Workers resolve the selected asset from its owned template. Scheduled/in-progress snapshots need explicit reporting; inventory other job statuses too, rather than silently discarding historical references.
- Template definitions and dispatch were checked in `template_definitions.py`, `template_workflow.py` and `routers/communications.py`.

An eventual authorized inventory must reconcile all these selections to their owning template's asset list, validate UUID, numeric ownership IDs, allowed MIME/type, positive bounded size and SHA-256, identify duplicate/conflicting metadata and dangling references, and count unique derived keys separately from reference occurrences. This preflight does not implement that data scan because complete authorized access is unavailable. Database metadata alone cannot establish whether local files or R2 objects exist; checking those objects is outside this request.

## Why existing credentials are insufficient

`f91c320ab006_verified_authorization.py` establishes FORCE RLS policies for runtime/control. Runtime access requires signed account/job scope. Control staff permissions cover specified administrative tables; they do not grant all-tenant template/campaign media inventory. A SQL SELECT permission or table-owner login is not proof of complete visibility under FORCE RLS. Application authorization establishment also uses database state; this script does not invoke it in a strictly read-only audit.

Required access: a security-owner-approved all-tenant reporting interface and explicitly authorized restricted read-only login covering template JSON and campaign snapshots under the existing RLS architecture. Its completeness and authorization must be reviewed before implementing a counting query. Do not disable RLS, use BYPASSRLS/superuser, assume function-owner roles, claim campaign jobs, or repurpose migration credentials. No policy, role, function or schema changes are made here.

## Exact Windows PowerShell command

Use the existing production **runtime** connection value privately; do not copy local development credentials or put a URL in command history. This script deliberately reads process environment only, never local `.env`.

```powershell
Set-Location 'D:\web apps\Python\CBD_Python'
$previousDatabaseUrl = $env:DATABASE_URL
$previousEnvironment = $env:ENVIRONMENT
$auditConnection = Read-Host 'Authorized production runtime DATABASE_URL' -AsSecureString
try {
    $env:DATABASE_URL = [System.Net.NetworkCredential]::new('', $auditConnection).Password
    $env:ENVIRONMENT = 'production'
    .\.venv\Scripts\python.exe scripts/audit_template_media.py
} finally {
    $env:DATABASE_URL = $previousDatabaseUrl
    $env:ENVIRONMENT = $previousEnvironment
    Remove-Variable auditConnection, previousDatabaseUrl, previousEnvironment
}
```

Expected exit code is **2 (blocked/incomplete)**, even when catalog checks succeed. All counts are JSON `null`. It is a connection/RLS preflight, not a completed inventory. It runs a read-only repeatable-read transaction, checks restricted login and catalog FORCE RLS flags/ownership, then rolls back. It reads no media, provider tokens, template contents or campaign payloads. It never prints credentials, URLs, raw database errors or SQL parameters. It never assumes a successful catalog check authorizes all-tenant access.

Do not enable production R2 based on this blocked report. An authorized complete inventory is still needed before deciding whether media copying is required.
