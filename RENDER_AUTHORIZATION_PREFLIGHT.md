# Render authorization installation preflight

Status: read-only installation prerequisite checks. The authorization implementation
and revisions `f91c320ab006` / `f91c320ab007` are now available locally. Follow
[the manual deployment guide](RENDER_AUTHORIZATION_DEPLOYMENT.md) after reviewing
the implementation. No existing database or Render deployment was changed.

The implementation must preserve FORCE RLS with NOSUPERUSER NOBYPASSRLS runtime,
control, and function-owner roles. Render documents support for `pgcrypto`:
https://render.com/docs/postgresql-extensions

The migration operator needs CREATE on the database and application schema,
ownership of existing application objects, and authorization to create or assume
the dedicated non-login function-owner roles. On PostgreSQL 16+, CREATEROLE alone
does not automatically grant SET ROLE to a newly created role. A function-owner
role must not be granted to either application login. A separate migration login
must not be placed in DATABASE_URL or CONTROL_DATABASE_URL.

## Run the read-only check

Run from the backend folder. Use the **external** Render connection URL of the
separate operator login when running from your Windows computer. Do not use a
runtime/control login and do not paste credentials into chat, source files or a
command literal. The script deliberately does not load `.env` or import the app.

```powershell
$operatorUrl = Read-Host 'Render operator connection URL (hidden)' -AsSecureString
try {
    $env:AUTHORIZATION_PREFLIGHT_URL = [System.Net.NetworkCredential]::new('', $operatorUrl).Password
    .\.venv\Scripts\python.exe scripts/render_authorization_preflight.py
} finally {
    Remove-Item Env:AUTHORIZATION_PREFLIGHT_URL -ErrorAction SilentlyContinue
    $operatorUrl.Dispose()
}
```

This performs catalog SELECTs inside a READ ONLY transaction, with query/connection
timeouts. It does not create an extension, role, table, grant, policy or migration.
It does not print the URL, password, signing secrets or raw exception messages.
The output includes role and table names and can be reviewed without credentials.

Exit codes:

- `0`: installation prerequisites satisfy the catalog checks. Listed manual
  requirements still need review; this does not certify the finished design.
- `1`: a privilege, ownership or application-role prerequisite is unsuitable.
- `2`: missing configuration, unsupported server, connection or query failure.

Return the JSON report for review. Do not change grants, enable bypass privileges,
or execute migrations to make this check pass without reviewing the report first.
If function-owner roles do not yet exist, this check reports their creation as a
manual requirement; it does not exercise role creation or ownership transfer.
Those operations must later be validated in a separate disposable database with
actual restricted logins before applying the reviewed migration to Render.

## Offline regression checks

```powershell
.\.venv\Scripts\python.exe tests/unit/test_render_authorization_preflight.py
```

These tests do not connect to PostgreSQL or load the application `.env`. They
verify rejection of inadequate privileges, unsafe application role attributes,
function-owner memberships, unavailable extensions and credential disclosure.
They are not RLS integration tests.
