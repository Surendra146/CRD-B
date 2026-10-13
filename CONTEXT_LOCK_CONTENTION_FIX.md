# Authorization context lock contention

The captured locks show control PID 254174 holding transaction 9207; runtime
PID 254173 waits for that transaction and subsequent control requests queue on
`hanuram_auth.contexts`. Pool exhaustion is a downstream symptom.

## Root cause and transaction lifecycle

`hanuram_auth.establish(text,text)` was the only function deleting expired
contexts. No Python code deletes them directly. Its global DELETE ran for every
signed authorization, including repeated authorizations in the same transaction.
It deleted committed contexts older than expiry plus five minutes and held row
locks until the caller committed or rolled back.

`get_control_db` yields a context-managed control session. `get_db` yields a
runtime session and closes it in `finally`. FastAPI caches these dependencies
within a request. Sessions begin lazily: `authorize` stores authority in session
info, opens a connection, and `after_begin` calls `apply_authority`, which signs
the current PID/transaction and calls `establish`. Reauthorization in an existing
transaction calls the same function again.

`get_current_user` establishes control `identity.user`, reads the user,
organization and tenant, establishes control `account`, then establishes runtime
`tenant` before the control session closes. Customer and segment handlers commit
runtime writes and refresh the created objects; refresh opens another scoped
transaction, with fresh authority installed by `after_begin`. The control
transaction is still open until dependency teardown. Close rolls back any
remaining transaction, including read/refresh transactions and failed requests;
successful mutations retain their explicit commits. No automatic commit was
added to dependency teardown, because it would commit work from failed requests.

An expired row deleted by control remains visible to runtime until control
commits. Runtime attempts the same DELETE and waits for control. Python cannot
finish authentication and close control until runtime authorization returns.
This is an application-level wait cycle, not necessarily a PostgreSQL-detected
deadlock: control is waiting in Python, not waiting on a database lock. Requests
behind the cycle hold more pooled connections. Cancelling the browser request
does not guarantee cancellation of a synchronous database operation.

Other paths reaching `establish` are registration/login/account edits, platform
staff operations, upload authorization, campaign claim/scope, and webhook
lookup/scope. Socket authentication uses the same overlapping identity/runtime
sessions. Webhooks keep the control lookup transaction while scoped runtime
sessions process changes. Campaign claiming commits discovery before runtime
dispatch. These paths use context managers or `finally` for closure; removing
the shared cleanup fixes the common lock hazard without changing their authority.

## Change

Revision `f91c320ab008` replaces `establish` with a frozen copy containing the
same authorization checks and transaction-local upsert, minus the global DELETE.
`context()` still rejects expired contexts using `statement_timestamp()` and
requires matching PID, transaction ID and login. Signature, installation,
subject, token issue time, tenant, staff permission, upload and job checks remain
unchanged. Existing function ownership and ACLs are retained by CREATE OR REPLACE.
No historical migration, RLS policy or connection-pool limit is changed.

Retention moves to `hanuram_auth.prune_contexts(integer)`. It deletes at most
1–10000 expired rows per call, preserves the five-minute grace period, and uses
`FOR UPDATE SKIP LOCKED`. It has a fixed search path and identity-owner ownership.
PUBLIC and application logins cannot execute it; the migration grants EXECUTE
only to the installation operator captured by `operator_staff`'s ACL. It rejects
an ambiguous/missing operator ACL. Function owners retain their existing trusted
administrative role access.

## Manual production rollout (not executed)

1. Back up the intended database. Confirm revision `f91c320ab007`. Review this
   migration against a restored copy with the same restricted roles and grants.
2. Stop backend/worker processes and pending traffic during the maintenance
   window. Old and new startup checks require different exact revisions.
3. Package both new revision/SQL files. Use the separate offline migration
   operator with the reviewed identity-owner SET/INHERIT authority and schema
   privileges, as described in `RENDER_AUTHORIZATION_DEPLOYMENT.md`. Never use
   application credentials or disable RLS to run migrations.
4. In that private operator process, explicitly run:

   ```powershell
   .\.venv\Scripts\python.exe -m alembic upgrade f91c320ab008
   ```

   `MIGRATION_DATABASE_URL` must already identify the intended production
   operator/database; this command changes that database. It is not a startup
   command. Downgrade is intentionally blocked because it restores the lock bug.
5. Start the updated backend/workers; startup now requires `f91c320ab008`. Check
   login, customer creation, segment creation, staff access and cross-tenant
   denial. Restarting stops old sessions; this patch does not kill captured PIDs.
   Do not terminate an old numeric PID without confirming its current identity.

## Retention operation

Run cleanup separately using the installation operator, with a short transaction
per batch. It is intentionally not scheduled inside a request or application
worker, and application credentials cannot invoke it.

```sql
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '10s';
SELECT hanuram_auth.prune_contexts(1000);
COMMIT;
```

After a failure, ROLLBACK before retrying. Repeat in separate committed batches
as needed. A zero result can mean eligible rows are locked; retry on the next
maintenance run. Establish a separate operator maintenance schedule and monitor
table growth. No cleanup schedule is installed automatically. Large accumulated
tables can make scans/sorting expensive; maintenance timeout and batching limit
impact, but an expiry index may warrant a separately reviewed future migration.
Expired rows do not grant access while awaiting cleanup.

## Verification

`scripts/run_authorization_sandbox.py --legacy-tests` initializes a disposable
loopback PostgreSQL cluster with generated credentials, applies revision 007,
reproduces the old control/runtime lock with a 500ms runtime lock timeout, then
applies revision 008 and runs restricted-role regressions. The test runner bounds
lock/statement waits only in the disposable test process. It does not consume
production URLs or modify existing databases.

Added regressions cover overlapping transactions with a locked expired row,
four concurrent authorizations, customer/segment HTTP mutations and error paths,
four concurrent customer/segment workflows, cross-tenant denial, expiration in
an open transaction and pooled reuse, dependency rollback/closure, and bounded
operator-only maintenance that skips locked rows. Existing signed-proof, RLS,
staff-audit, upload/job and webhook cases still run. A unit test verifies the
replacement `establish` changes only the cleanup statement.

Remaining limits: the captured PID-to-request pairing cannot be reconstructed
from hidden activity fields, but the same wait mechanism is reproducible. Other
business-row locks, long external calls and workload-driven pool pressure are
outside this fix. Production migration and live smoke checks remain manual.

Validated on a disposable PostgreSQL 18.6 cluster: pre-fix blocking reproduction
passed; all 33 restricted-role tests passed; the legacy unit/API suite passed
230 tests and 6 subtests. The suite emitted one existing Starlette TestClient
deprecation warning. The initial new HTTP fixture used a phone longer than the
API permits; correcting it to the required ten digits allowed the full final
run to pass. The frozen-function comparison also passed independently.
