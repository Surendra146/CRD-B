# Local/production configuration audit — 2026-10-25

## Current verified local state

- Windows PostgreSQL database: `hanuram_dev`.
- Runtime connection: `hanuram_runtime`; control connection: `hanuram_control`.
- Both connections report Alembic `f91c320ab012`, matching the repository head.
- Docker backend runs `ENVIRONMENT=development`, with FORCE RLS required,
  automatic schema creation disabled and WhatsApp sending disabled.
- Frontend `http://localhost:5173` and backend `/ready` at
  `http://localhost:8000/ready` returned HTTP 200.
- Shared Redis: `cbd-redis-1`, available to containers as `redis:6379` and Windows
  processes as `127.0.0.1:6379`. No Celery consumers or Beat were started.

The backend `.env` uses loopback database connections. The frontend repository's
private `.env.docker` uses `host.docker.internal` to reach the same Windows DB.
These private settings contain local credentials and are not reproduced here.

## Configuration corrections

- `render.yaml` now identifies hosted production as `hanuram_production_ii23`,
  provisioning operator `hanuram_production_user`; application URLs still need
  restricted `hanuram_runtime` and `hanuram_control` credentials. Environment is
  production and sending remains disabled. Resource name retained; do not sync
  this file to recreate or rename an existing resource.
- Added secret-free `.env.production.example`; development and production
  examples are explicitly permitted by `.gitignore`.
- Moved the two production operator URL settings out of auto-loaded `.env` into
  private `.env.production.operator.local`. Git confirms both private files are
  ignored. The operator file is not loaded automatically by the app or scripts.
  Supply operator credentials only to an explicitly authorized operator process;
  never use them for runtime services.
- Corrected operational database names and release-head instructions in
  `LOCAL_DATABASE_SETUP.md` and `RENDER_AUTHORIZATION_DEPLOYMENT.md`.
- Marked older audit reports' database conflicts as historical. Old revision
  discussions, archival schema artifacts and migration compatibility allowlists
  remain historical evidence; they are not active connection settings.
- Both Compose files address the same `cbd` Redis service/volume, avoiding the
  previous duplicate. Frontend `.env.docker.example` now documents correct local
  roles/database instead of creating a separate `cm_db` instance.

Production **file configuration** was reviewed/corrected. The actual hosted
database revision, live service secrets, permissions and deployed commit were not
queried or changed. Therefore local is verified current; live production freshness
remains unverified. No migrations, resets, media deletion, production deployment
or real WhatsApp messages occurred.

## Docker cleanup completed

Removed obsolete containers: `hanuram-local-redis-1`, `hanuram-dev-redis`,
`cbd-frontend-prod-1`, `cbd-backend-prod-1`, `cbd-postgres-1`.
Removed their unused image tags: `cbd-frontend-prod`, `cbd-backend-prod`,
`postgres:17-alpine`. No force removal, system prune or volume deletion.

Only the current three containers remain: `cbd-frontend-dev-1`,
`cbd-backend-dev-1`, `cbd-redis-1`. Old PostgreSQL/Redis volumes remain preserved
for recovery. Do not merge obsolete broker data into the current queue.

PostgreSQL itself runs on Windows, so `hanuram_dev` will not appear as a separate
Docker database container. The `cbd` label is the Compose project name and does
not select a database.

## Validation

Read-only SQL verified both local identities and migration revisions. HTTP checks
passed. Compose validation and service health checks passed. Relevant configuration,
authorization-preflight and interlock tests: **52 passed, six subtests passed**;
one existing Starlette/httpx deprecation warning. Scoped diff whitespace checks
passed. No claim is made that the live Render environment is up to date.
