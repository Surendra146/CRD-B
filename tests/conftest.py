"""Tests never connect to the application's configured database."""
import os
from uuid import uuid4

import pytest

# Override before application imports and load_dotenv.
os.environ.update({
    "ENVIRONMENT": "test",
    "DATABASE_URL": "postgresql+psycopg://test:test@127.0.0.1:1/unused_test",
    "JWT_SECRET": "pytest-only-secret-not-for-production-000000",
    "ENABLE_REDIS_PROGRESS": "false",
    "ENABLE_SOCKET_PROGRESS": "false",
    "AUTO_CREATE_TABLES": "false",
    "CORS_ORIGINS": "https://frontend.example.com",
})


def pytest_addoption(parser):
    parser.addoption("--require-db", action="store_true", help="Fail if TEST_DATABASE_URL is missing")


def pytest_configure(config):
    if config.getoption("--require-db") and not os.getenv("TEST_DATABASE_URL"):
        raise pytest.UsageError("--require-db requires TEST_DATABASE_URL pointing to a dedicated *_test PostgreSQL database")


@pytest.fixture(scope="session")
def test_engine():
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url
    from sqlalchemy.schema import CreateSchema, DropSchema
    from app.database.connection import Base
    import app.models  # Register metadata.

    raw_url = os.getenv("TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip("Set TEST_DATABASE_URL to a dedicated *_test PostgreSQL database")
    url = make_url(raw_url)
    if url.get_backend_name() != "postgresql" or not (url.database or "").endswith("_test"):
        raise pytest.UsageError("Tests require PostgreSQL and a database name ending in _test")
    engine = create_engine(url.set(drivername="postgresql+psycopg"), pool_pre_ping=True)
    schema = "pytest_" + uuid4().hex
    with engine.begin() as connection:
        connection.execute(CreateSchema(schema))
    scoped_engine = engine.execution_options(schema_translate_map={None: schema})
    try:
        Base.metadata.create_all(scoped_engine)
        yield scoped_engine
    finally:
        with engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        engine.dispose()


@pytest.fixture
def session_factory(test_engine):
    from sqlalchemy.orm import sessionmaker

    with test_engine.connect() as connection:
        transaction = connection.begin()
        factory = sessionmaker(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
        try:
            yield factory
        finally:
            transaction.rollback()


@pytest.fixture
def db_session(session_factory):
    with session_factory() as session:
        yield session


@pytest.fixture
def client(session_factory, monkeypatch):
    from fastapi.testclient import TestClient
    from app.database.connection import get_db
    from app.config.settings import get_settings
    import app.main as main

    get_settings.cache_clear()
    monkeypatch.setattr(main, "SessionLocal", session_factory)
    app = main.create_app()

    def override_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app, base_url="https://testserver") as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()


@pytest.fixture
def account_factory(client):
    def create_account():
        unique = uuid4().hex
        payload = {"email": f"user-{unique}@example.com", "password": "Test-password-123!", "name": "Test owner", "companyName": f"Company {unique}"}
        response = client.post("/api/auth/register", json=payload)
        assert response.status_code == 200, response.text
        body = response.json()
        return {"payload": payload, "user": body["data"], "headers": {"Authorization": "Bearer " + body["token"]}}
    return create_account


@pytest.fixture
def account(account_factory):
    return account_factory()


@pytest.fixture
def customer_payload():
    return {"externalId": "CUST-001", "name": "Asha Rao", "phone": "9876543210", "address": "12 Main Road", "customerCreatedDate": "2026-10-03", "tags": ["vip"], "demographics": {"city": "Pune"}}
