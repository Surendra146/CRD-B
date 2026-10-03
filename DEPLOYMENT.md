# Deployment review and operating instructions

Backend: `D:\web apps\Python\CBD_Python` / `Surendra146/CRD-B`.
Frontend: `D:\web apps\React\CBD project` / `Surendra146/CRD-F`.
Both deploy from `main`. Render uses native Python and a static frontend;
Docker Compose is a separate self-hosted deployment path.

## Before a production release

- Rotate any credentials previously committed in the backend `.env`. Removing
  the file from the Git index does not remove it from history. Local files are preserved.
- Set backend Render `CORS_ORIGINS` to the exact HTTPS frontend origin,
  with no trailing slash. Use comma-separated origins for additional trusted domains.
- Set frontend Render `VITE_BACKEND_URL` and `VITE_API_URL` to the backend HTTPS
  origin (no `/api` suffix). Vite embeds these public values at build time, so
  rebuild after changes. Never place secrets in `VITE_*` variables.
- Ensure backend `DATABASE_URL` and a random `JWT_SECRET` of at least 32 characters
  are set. Render Blueprint generates the JWT secret for a new service.
- Keep `ENABLE_SOCKET_PROGRESS=false` and frontend
  `VITE_ENABLE_SOCKET_PROGRESS=false` in production until socket connection and
  upload-room subscriptions enforce authentication and tenant authorization.
- Password reset is blocked with HTTP 501 until a verified, expiring, single-use
  token flow and delivery mechanism exist. Existing plain-text passwords are
  hashed on successful login; rotate passwords previously exposed in storage or API responses.
- The Blueprint still specifies free Postgres. Select an appropriate paid
  database and web-service plan, backups, retention, restore testing and monitoring
  before treating this as a durable production service. No paid resources were provisioned.
- The current Alembic initial revision and current models differ. Startup
  `create_all` creates missing tables but does not migrate existing columns.
  Keep the existing bootstrap behavior until database state is inspected and
  an additive migration/baseline is reviewed against a restored database copy.
  Do not run the initial migration blindly against existing tables.
- Pin and review Python dependency versions and container image digests for a
  reproducible release; current requirements use version ranges.

## CI and Render

Backend CI runs pytest unit and PostgreSQL API tests with coverage/JUnit reports
and Docker builds. See [tests/README.md](tests/README.md) for local commands and
database isolation details. Frontend CI runs strict lint, a production build and Docker build.
These workflow files must be committed to their respective repositories.
In both Render services, save Auto-Deploy as **After CI Checks Pass** before pushing.
For existing manually configured services, editing `render.yaml` alone does not
apply settings: update them in the dashboard or sync the connected Blueprint.

```powershell
cd "D:\web apps\Python\CBD_Python"
git status
git add .
git diff --cached --stat
git commit -m "Harden backend deployment and security"
git push origin main

cd "D:\web apps\React\CBD project"
git status
git add .
git diff --cached --stat
git commit -m "Harden frontend deployment configuration"
git push origin main
```

Review all staged changes, including pre-existing dashboard deletions. No commit,
push or Render deployment was performed during this review.

## Docker

Start Docker Desktop with the Linux engine, then from the frontend directory:

```powershell
npm.cmd run docker:init
npm.cmd run docker:test
npm.cmd run docker:prod
npm.cmd run docker:logs
```

`docker:init` preserves an existing `.env.docker`; ensure its database and JWT
secrets are strong. Compose resolves the backend at `../../Python/CBD_Python`,
which matches this workspace layout. Postgres and Redis are not publicly exposed.
The production frontend exposes port 80 and proxies API requests to the backend.
For an Internet deployment add HTTPS termination, persistent-volume backups,
host monitoring and controlled release/rollback procedures. Keep one backend
worker while progress state is process-local.

## Verification scope

Local security tests, Python dependency consistency and frontend lint/build passed.
After Docker Desktop started, backend and frontend test containers and both
production image builds passed. An isolated `cbd-validation` Compose stack with
a fresh database reached healthy status for frontend, backend, Postgres and Redis.
HTTP smoke checks passed for the frontend, SPA routes, API proxy/health,
registration, login, authenticated profile, secure cookie, credential filtering,
rejected invalid access/reset and CORS trusted/untrusted origins.
The existing `cbd` stack and its database were left untouched; temporary
validation containers and volumes were removed after testing.
Live GitHub and Render settings, existing production database migrations and a
full browser/upload workflow remain unverified.

To repeat HTTP checks, start an isolated Compose stack from the frontend directory
with `$env:FRONTEND_PORT='18080'` and `docker compose --env-file .env.docker
-p cbd-validation --profile prod up --build -d --wait`. Then run
`.venv/Scripts/python.exe scripts/docker_smoke.py` from the backend directory.
The smoke script creates a random test account only at `localhost:18080`.

References: https://render.com/docs/deploys,
https://render.com/docs/blueprint-spec, https://vite.dev/guide/.
