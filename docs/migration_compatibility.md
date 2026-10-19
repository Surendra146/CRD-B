# Strict migration compatibility

`app/database/migrations.py` reads the deployed `alembic.ini` using Alembic Config
and ScriptDirectory, resolving relative script locations from the backend root.
It compares all deployed heads with all rows in `public.alembic_version`.
Both sets must be nonempty, valid, and equal. Multiple heads are supported.
Metadata is read afresh; adding a migration requires no application constant update.
The validator does not execute env.py, run migrations, load operator credentials,
commit, or close the caller's connection. Missing metadata/table, query failures,
and mismatches fail closed with sanitized diagnostics.

The existing RLS startup authorization check invokes this for runtime and control
connections. Their existing connection context managers retain ownership/cleanup.
With REQUIRE_RLS enabled, /ready rechecks both connections so later schema changes
return 503. /health and other readiness dependencies retain their existing behavior.
Role checks, RLS, and authorization signing remain unchanged.

## Render deployment (manual approval required)

1. Review the diff and test results. Package alembic.ini and the entire alembic/
   directory with the backend; keep existing role credentials and environment.
2. In staging, verify the deployed artifact heads and SELECT version_num FROM
   public.alembic_version on the intended database. Compare revision sets, not
   lexical order or numeric revision suffixes.
3. Back up production before any separately reviewed migration. If production
   already matches the artifact heads, this change needs no database migration.
   Otherwise review the migration plan separately using the migration/operator
   role; never stamp the version table to bypass validation. Do not automatically
   upgrade head. Coordinate schema changes with deployment: strict equality can
   intentionally make the previous backend unready during migration.
4. After explicit approval, push/deploy the reviewed backend. No new environment
   variables or privileged application credentials are needed.
5. Confirm startup finishes, /health returns 200, /ready returns 200, and login
   works. A mismatch produces expected/actual revision diagnostics and fails closed.

## Rollback

Roll back to a backend artifact compatible with the database's current heads.
Do not blindly redeploy an older artifact expecting an older schema; it will
correctly reject the database. This validator-only change requires no schema
downgrade. If a separate migration was applied, review its rollback and backup
restore plan independently before any database operation. Never edit alembic_version
manually or disable RLS/validation to force startup.

## Local verification

Run pytest tests/unit/test_migration_compatibility.py. These tests use temporary
Alembic graphs, mocked connections, and in-memory SQLite for connection cleanup;
they do not contact production or certify live PostgreSQL permissions/RLS.
