# Separate local and production databases

## Local Redis with Docker

### Full local frontend/backend stack

The frontend repository's `docker-compose.yml` now uses development services and
the existing Windows PostgreSQL database `hanuram_dev`. Its private `.env.docker`
contains `LOCAL_DATABASE_URL` for `hanuram_runtime` and
`LOCAL_CONTROL_DATABASE_URL` for `hanuram_control`, using `host.docker.internal`.
Local authorization keys must match that database. The backend `.env` continues
using loopback for Python processes started directly on Windows.

```powershell
Set-Location 'D:\web apps\React\CBD project'
docker compose --env-file .env.docker --profile dev up --build -d --wait redis backend-dev frontend-dev
```

Frontend: `http://localhost:5173`; backend: `http://localhost:8000` (or the
`BACKEND_PORT` configured in `.env.docker`). This stack's internal Redis hostname
is `redis`; it does not need a published port. No worker or Beat service is started.
`WHATSAPP_SENDING_ENABLED=false`, `REQUIRE_RLS=true` and
`AUTO_CREATE_TABLES=false` are explicit. There is no automatic migration/reset.

The old `cm_db` volume is retained for recovery after obsolete containers are removed;
they are not the new application's database. A Compose project/image or Linux
account name containing `cbd` does not select a PostgreSQL database. Do not use
`down --volumes` or `--remove-orphans` to clean up the old stack. The old
`docker:prod` npm command is now a compatibility alias for `docker:dev` in this
local frontend repository; actual hosted Render deployments remain separate.

For future local key/password changes, update the private `.env.docker` values
consistently; its copied connection values do not track backend `.env` edits
automatically. Never replace local URLs/keys with hosted production credentials.

### Redis only, with Python running directly on Windows

`compose.yaml` starts only the shared `cbd-redis-1`, bound to Windows loopback.
It uses the same project/service/volume as the frontend Compose stack, avoiding a second Redis. It does not create,
reset or migrate PostgreSQL. The backend connects to your existing local
`hanuram_dev` database as `hanuram_runtime`, with `hanuram_control` for the separate
control connection. Review `.env.development.example` and merge the local values
into `.env`, preserving existing local authorization/encryption keys. Change port
5432 if your local PostgreSQL uses another port; URL-encode passwords.

```powershell
Set-Location 'D:\web apps\Python\CBD_Python'
docker compose -f compose.yaml up -d redis
docker compose -f compose.yaml exec redis redis-cli ping
# Expected: PONG
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload
```

These are operator instructions; no services are started by editing these files.
Keep `WHATSAPP_SENDING_ENABLED=false`. Workers/Beat can be started separately only
when intended; they are not started by this Compose file. The FastAPI process runs
on Windows, so `REDIS_URL=redis://127.0.0.1:6379/0` is correct. Redis does not connect
to PostgreSQL. If the backend is later containerized, its Windows PostgreSQL host
must be `host.docker.internal`, and its Redis host must be the Compose service
`redis`; container loopback is not the Windows host.

To stop Redis while retaining its data: `docker compose -f compose.yaml stop redis`.
Do not remove volumes to troubleshoot connectivity. If port 6379 is occupied,
inspect the existing service before starting another Redis instance.

`render.yaml` configures hosted services, not local Docker. Its current database
name/user edits are retained, but its `databases.user` is a provisioning login and
does not configure the restricted application role. Never sync it to rename an
existing hosted database or make the runtime login its privileged owner. Configure
the existing runtime/control URLs through the shared Render environment group.

Use `hanuram_dev` on local PostgreSQL 18 and `hanuram_production_ii23` on the production server. You do not need a second local PostgreSQL instance or a locally named production database. The application does not require the same database name in both environments.

The local setup wrapper and `--local-development` key-provisioning flag support this arrangement. The existing production setup commands still default to `hanuram_production_ii23`. These tools do not switch the running application's connection; its environment does.

## 1. Stop the local backend and configure local URLs

In your local `.env`, replacing placeholders with local role passwords:

```dotenv
ENVIRONMENT=development
REQUIRE_RLS=true
AUTO_CREATE_TABLES=false
DATABASE_URL=postgresql+psycopg://hanuram_runtime:RUNTIME_PASSWORD@127.0.0.1:5432/hanuram_dev
CONTROL_DATABASE_URL=postgresql+psycopg://hanuram_control:CONTROL_PASSWORD@127.0.0.1:5432/hanuram_dev
CAMPAIGN_TRANSPORT=database
DATABASE_AUTH_IDENTITY_KEY=LOCAL_IDENTITY_KEY
DATABASE_AUTH_STAFF_KEY=LOCAL_STAFF_KEY
DATABASE_AUTH_JOBS_KEY=LOCAL_JOBS_KEY
```

Use the actual local port if different from 5432. URL-encode password special characters. The roles `hanuram_runtime` and `hanuram_control` must exist on the local PostgreSQL server with the reviewed restricted grants. They are database login names, not database names. Production can use the same role names on its separate server, with different passwords and keys.

Keep the production connection settings in the hosting service environment. Do not copy production credentials or signing keys into your local installation.

## 2. Check the existing database before installation

Your earlier error indicates that `hanuram_dev` already contains an authorization guard. Do not recreate or drop that database, rerun initial key provisioning blindly, or assume a fresh setup.

In pgAdmin, select the **local** server and `hanuram_dev`, using your offline local administrator, and inspect:

```sql
SELECT current_database(), session_user;
SELECT version_num FROM alembic_version;
SELECT rolname, rolcanlogin, rolsuper, rolbypassrls
FROM pg_roles
WHERE rolname IN ('hanuram_dev_user', 'hanuram_runtime', 'hanuram_control',
                 'hanuram_identity_owner', 'hanuram_staff_owner', 'hanuram_jobs_owner');
SELECT to_regclass('hanuram_auth.signing_keys');
```

If the last query finds the table, check only whether keys exist:

```sql
SELECT count(*) AS configured_key_count FROM hanuram_auth.signing_keys;
```

Three existing keys mean your `.env` needs the matching local keys. Newly generated keys will not match. The provisioning script intentionally refuses to overwrite existing keys; use a reviewed rotation procedure if existing local values have been lost. Do not display or share the key table contents.

## 3. Initial role preparation, only if not already installed

For a fresh/unprepared local installation, an offline administrator must provision restricted application logins and a separate `hanuram_dev_user` operator. The application logins must not own tables, inherit function-owner roles, or have SUPERUSER/BYPASSRLS/CREATEROLE/CREATEDB privileges. The offline operator requires the ownership and installation privileges needed by the migrations. Creating role names alone is not enough for an already migrated database whose objects belong to another operator; review that ownership before proceeding.

After these prerequisites are satisfied, use the local wrapper:

```powershell
cd 'D:\web apps\Python\CBD_Python'
$pgBin = 'C:\Program Files\PostgreSQL\18\bin'
& "$pgBin\psql.exe" -h 127.0.0.1 -p 5432 -U hanuram_dev_user -d hanuram_dev -v ON_ERROR_STOP=1 -f scripts/local_authorization_operator.sql
```

This wrapper checks for `hanuram_dev` and a direct `hanuram_dev_user` operator connection. It runs the same reviewed role/schema preparation as production, without dropping tables or disabling guards. The production setup script still defaults to checking `hanuram_production_ii23` when invoked normally.

## 4. Pending local migrations

With a properly provisioned local operator, apply only pending migrations:

```powershell
$env:MIGRATION_DATABASE_URL = 'postgresql+psycopg://hanuram_dev_user:LOCAL_OPERATOR_PASSWORD@127.0.0.1:5432/hanuram_dev'
.venv\Scripts\python.exe -m alembic current
.venv\Scripts\python.exe -m alembic upgrade head
```

If the existing local migrations were installed under another owner, resolve the operator's required ownership/grants first. Do not use a blanket ownership reassignment across PostgreSQL databases or change the recorded Alembic revision to skip required installation steps.

## 5. Initial local keys, only when no keys exist

Generate three separate local values and save them in your local `.env`:

```powershell
.venv\Scripts\python.exe -c "import secrets; print('DATABASE_AUTH_IDENTITY_KEY='+secrets.token_urlsafe(48)); print('DATABASE_AUTH_STAFF_KEY='+secrets.token_urlsafe(48)); print('DATABASE_AUTH_JOBS_KEY='+secrets.token_urlsafe(48))"
```

Provision those exact values once:

```powershell
$env:OPERATOR_DATABASE_URL = $env:MIGRATION_DATABASE_URL
.venv\Scripts\python.exe scripts/provision_database_authorization_keys.py --apply --local-development
```

Paste the corresponding values into the three hidden prompts. Local mode checks localhost, `hanuram_dev` and `hanuram_dev_user`, then verifies the actual database/session and existing authorization table ownership before inserting anything. Production key provisioning is unchanged when `--local-development` is omitted.

## 6. Start local development

Remove offline credentials from the shell environment if you set them above:

```powershell
Remove-Item Env:MIGRATION_DATABASE_URL -ErrorAction SilentlyContinue
Remove-Item Env:OPERATOR_DATABASE_URL -ErrorAction SilentlyContinue
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Both application connections must target `hanuram_dev` and its same authorization installation. Startup verifies restricted roles, policies and signing-key configuration. `REQUIRE_RLS=true` enables these checks; it does not create roles, repair grants or provision keys.

The frontend's local API origin should target `http://127.0.0.1:8000`; start it with `npm.cmd run dev` from the frontend repository.

## Change verification

The local-mode changes were checked with `tests/unit/test_local_authorization_setup.py` and `tests/unit/test_render_authorization_preflight.py`: 28 tests and six subtests passed. `git diff --check` passed. These were mocked/unit checks, not execution of either database installation. No local or production database, signing keys, migrations or environment credentials were changed by this implementation.
