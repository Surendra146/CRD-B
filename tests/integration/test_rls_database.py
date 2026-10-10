import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.database.tenancy import bind_scope

pytestmark = pytest.mark.integration
REVISIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


@pytest.fixture
def restricted_database(test_engine):
    with test_engine.connect().execution_options(schema_translate_map=None) as connection:
        transaction = connection.begin()
        schema = "rls_test_" + uuid4().hex
        role = "rls_runtime_" + uuid4().hex
        try:
            connection.execute(text(f"CREATE SCHEMA {schema}"))
            connection.execute(text(f"SET LOCAL search_path TO {schema}"))
            with Operations.context(MigrationContext.configure(connection)):
                for name in ["62942c9db687_initial_database_schema.py", "d24bf074d970_tenant_whatsapp_connections.py",
                             "e73a2109b001_repair_tenant_schema.py", "f91c320ab002_saas_schema.py", "f91c320ab003_force_tenant_rls.py"]:
                    spec = importlib.util.spec_from_file_location("rls_revision", REVISIONS / name)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    module.upgrade()
            # Seed before switching to the unprivileged runtime role.
            connection.execute(text("""INSERT INTO tenants (id, name, is_active, settings, created_at, updated_at)
                VALUES (1, 'First tenant', true, '{}', now(), now()), (2, 'Second tenant', true, '{}', now(), now())"""))
            connection.execute(text("""INSERT INTO organizations (id, name, tenant_id, members, custom_roles, settings, branding, limits, usage, created_at, updated_at)
                VALUES (11, 'First organization', 1, '[]', '[]', '{}', '{}', '{}', '{}', now(), now()),
                       (22, 'Second organization', 2, '[]', '[]', '{}', '{}', '{}', '{}', now(), now())"""))
            connection.execute(text("""INSERT INTO customers (id, tenant_id, organization_id, name, demographics, lifecycle, purchases, interactions, follow_up, preferences, tags, source, module_tags, is_active, created_at, updated_at)
                VALUES (101, 1, 11, 'First customer', '{}', '{}', '[]', '[]', '{}', '{}', '[]', '{}', '[]', true, now(), now()),
                       (202, 2, 22, 'Second customer', '{}', '{}', '[]', '[]', '{}', '{}', '[]', '{}', '[]', true, now(), now())"""))
            connection.execute(text(f"CREATE ROLE {role} NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT"))
            connection.execute(text(f"GRANT USAGE ON SCHEMA {schema} TO {role}"))
            connection.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {schema} TO {role}"))
            connection.execute(text(f"SET LOCAL ROLE {role}"))
            yield connection
        finally:
            transaction.rollback()  # Includes role/schema creation, not application data.


def test_raw_sql_without_tenant_context_cannot_read_customer_rows(restricted_database):
    assert restricted_database.execute(text("SELECT id FROM customers")).all() == []


def test_raw_sql_and_orm_only_return_current_tenant(restricted_database):
    from app.models import Customer
    from sqlalchemy import select
    session = Session(bind=restricted_database, join_transaction_mode="create_savepoint")
    bind_scope(session, 1, 11)
    assert session.execute(text("SELECT id FROM customers")).scalars().all() == [101]
    assert [row.id for row in session.scalars(select(Customer))] == [101]
    assert session.get(Customer, 202) is None
    session.close()


def test_cross_tenant_write_fails_even_when_query_forgets_filter(restricted_database):
    with Session(bind=restricted_database, join_transaction_mode="create_savepoint") as session:
        bind_scope(session, 1, 11)
        assert session.execute(text("UPDATE customers SET name='Attempted' WHERE id=202")).rowcount == 0
        with pytest.raises(DBAPIError):
            session.execute(text("UPDATE customers SET tenant_id=2, organization_id=22 WHERE id=101"))
        session.rollback()


def test_scope_is_renewed_after_commit_and_cleared_for_next_session(restricted_database):
    with Session(bind=restricted_database, join_transaction_mode="create_savepoint") as session:
        bind_scope(session, 1, 11)
        assert session.scalar(text("SELECT count(*) FROM customers")) == 1
        session.commit()
        assert session.scalar(text("SELECT id FROM customers")) == 101
    with Session(bind=restricted_database, join_transaction_mode="create_savepoint") as session:
        assert session.scalar(text("SELECT count(*) FROM customers")) == 0
        bind_scope(session, 2, 22)
        assert session.scalar(text("SELECT id FROM customers")) == 202


def test_composite_organization_fk_rejects_mixed_scope(restricted_database):
    with Session(bind=restricted_database, join_transaction_mode="create_savepoint") as session:
        bind_scope(session, 1, 22)
        with pytest.raises(DBAPIError):
            session.execute(text("""INSERT INTO customers (id, tenant_id, organization_id, name, demographics, lifecycle, purchases, interactions, follow_up, preferences, tags, source, module_tags, is_active, created_at, updated_at)
                VALUES (303, 1, 22, 'Mismatched', '{}', '{}', '[]', '[]', '{}', '{}', '[]', '{}', '[]', true, now(), now())"""))
        session.rollback()


def test_legacy_business_profiles_are_backfilled_without_changing_ownership(test_engine):
    with test_engine.connect().execution_options(schema_translate_map=None) as connection:
        transaction = connection.begin()
        schema = "profile_test_" + uuid4().hex
        try:
            connection.execute(text(f"CREATE SCHEMA {schema}"))
            connection.execute(text(f"SET LOCAL search_path TO {schema}"))
            with Operations.context(MigrationContext.configure(connection)):
                for name in ["62942c9db687_initial_database_schema.py", "d24bf074d970_tenant_whatsapp_connections.py", "e73a2109b001_repair_tenant_schema.py"]:
                    spec = importlib.util.spec_from_file_location("profile_revision", REVISIONS / name)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    module.upgrade()
                connection.execute(text("INSERT INTO tenants (id,name,is_active,settings,created_at,updated_at) VALUES (1,'Existing',true,'{}',now(),now())"))
                connection.execute(text("INSERT INTO organizations (id,name,tenant_id,members,custom_roles,settings,branding,limits,usage,created_at,updated_at) VALUES (11,'Existing business',1,'[]','[]','{}','{}','{}','{}',now(),now())"))
                spec = importlib.util.spec_from_file_location("profile_revision", REVISIONS / "f91c320ab002_saas_schema.py")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                module.upgrade()
            assert connection.execute(text("SELECT tenant_id, organization_id, legal_name FROM business_profiles")).one() == (1,11,'Existing business')
            assert connection.scalar(text("SELECT tenant_id FROM organizations WHERE id=11")) == 1
        finally:
            transaction.rollback()
