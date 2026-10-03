# Backend pytest suite

Install the test tools in the project's virtual environment:

```powershell
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m pytest -m "not integration" -q
```

Unit tests cover password hashing/limits, JWT expiry/signatures, production
configuration and credential filtering. API tests exercise the real FastAPI
routes, startup/shutdown and PostgreSQL: authentication, legacy password upgrade,
password change/reset, customer CRUD/JSONB, duplicates, validation and tenant isolation.

## Run all tests with PostgreSQL

Use a dedicated test database whose name ends in `_test`. The suite does not
read the application database URL from `.env`. It creates a randomly named schema
and drops only that schema afterward. Each test rolls back an outer transaction;
route-handler commits operate on savepoints. Integration tests skip when no test
URL is supplied. `--require-db` makes a missing URL an error and is required in CI.

Start a disposable container with no persistent volume:

```powershell
docker run --rm -d --name cbd-pytest-db -p 127.0.0.1:15433:5432 -e POSTGRES_DB=cbd_test -e POSTGRES_USER=cbd -e POSTGRES_PASSWORD=pytest-test-only postgres:17-alpine
docker exec cbd-pytest-db pg_isready -U cbd -d cbd_test
$env:TEST_DATABASE_URL='postgresql+psycopg://cbd:pytest-test-only@127.0.0.1:15433/cbd_test'
.venv/Scripts/python.exe -m pytest --require-db --cov=app --cov-report=term-missing --cov-report=html --junitxml=test-results/pytest.xml
docker stop cbd-pytest-db
Remove-Item Env:TEST_DATABASE_URL
```

Wait until `pg_isready` reports accepting connections before running the suite.
Do not reuse the application database or point a test URL at production.
Coverage reports are ignored by Git; HTML output is in `htmlcov/index.html`.
The suite currently covers authentication and customer flows; upload processing,
external provider calls and remaining modules still need dedicated tests.

## Docker and CI

```powershell
docker build --target test -t cbd-backend:pytest .
docker run --rm cbd-backend:pytest
```

The Docker test target runs unit tests by default; production images do not
include test dependencies. To run API tests in Docker, pass `TEST_DATABASE_URL`
reachable from that container and override the command with
`python -m pytest --require-db -p no:cacheprovider`.
GitHub Actions supplies its own PostgreSQL service, runs the full suite and
uploads coverage XML and JUnit reports, including when tests fail.

Fixture/transaction references:
https://docs.pytest.org/en/stable/how-to/fixtures.html
https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#joining-a-session-into-an-external-transaction-such-as-for-test-suites

## Validation performed

35 tests passed against a disposable PostgreSQL 17 database (15 unit cases,
20 API integration cases). Overall application coverage was 51%, with 88%
for the security service. The updated Docker test image built successfully;
executing the new pytest suite inside Docker was not approved during this run.
Existing datetime and TestClient dependency deprecation warnings remain visible.
VS Code is configured to discover pytest tests in its Testing panel.
