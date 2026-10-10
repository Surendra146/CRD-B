"""Exercise real legacy-schema repairs; all DDL is rolled back in a *_test database."""
import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect, text

pytestmark = pytest.mark.integration
REVISIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def revision(name):
    spec = importlib.util.spec_from_file_location("migration_under_test", REVISIONS / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def legacy_database(test_engine):
    with test_engine.connect().execution_options(schema_translate_map=None) as connection:
        transaction = connection.begin()
        schema = "migration_test_" + uuid4().hex
        try:
            connection.execute(text(f"CREATE SCHEMA {schema}"))
            connection.execute(text(f"SET LOCAL search_path TO {schema}"))
            with Operations.context(MigrationContext.configure(connection)):
                revision("62942c9db687_initial_database_schema.py").upgrade()
                revision("d24bf074d970_tenant_whatsapp_connections.py").upgrade()
                yield connection, schema
        finally:
            transaction.rollback()


def repair():
    revision("e73a2109b001_repair_tenant_schema.py").upgrade()


def test_repair_upgrades_empty_legacy_schema(legacy_database):
    connection, schema = legacy_database
    repair()
    inspector = inspect(connection)
    for table in ["customers", "campaigns", "data_uploads", "data_upload_rows", "segments", "whatsapp_templates"]:
        tenant_column = next(c for c in inspector.get_columns(table, schema=schema) if c["name"] == "tenant_id")
        assert tenant_column["nullable"] is False
    assert {"whatsapp_bulk_jobs", "whatsapp_auto_responders", "gmaps_extracted_leads", "whatsapp_group_tasks"} <= set(inspector.get_table_names(schema=schema))
    repair()  # Supports deployments that already created some tables/columns.


def seed_legacy_customer(connection, organization_tenant="1"):
    connection.execute(text("""INSERT INTO tenants (id, name, is_active, settings, created_at, updated_at)
        VALUES (1, 'Legacy business', true, '{}', now(), now())"""))
    connection.execute(text(f"""INSERT INTO organizations (id, name, tenant_id, members, custom_roles, settings, branding, limits, usage, created_at, updated_at)
        VALUES (10, 'Legacy organization', {organization_tenant}, '[]', '[]', '{{}}', '{{}}', '{{}}', '{{}}', now(), now())"""))
    connection.execute(text("""INSERT INTO customers (id, organization_id, name, demographics, lifecycle, purchases, interactions, follow_up, preferences, tags, source, module_tags, is_active, created_at, updated_at)
        VALUES (20, 10, 'Preserved customer', '{}', '{}', '[]', '[]', '{}', '{}', '[]', '{}', '[]', true, now(), now())"""))


def test_repair_preserves_ids_and_backfills_only_from_organization(legacy_database):
    connection, schema = legacy_database
    seed_legacy_customer(connection)
    repair()
    row = connection.execute(text("SELECT id, organization_id, tenant_id, name FROM customers")).one()
    assert tuple(row) == (20, 10, 1, "Preserved customer")


def test_repair_refuses_unresolved_legacy_ownership(legacy_database):
    connection, schema = legacy_database
    seed_legacy_customer(connection, "NULL")
    with pytest.raises(RuntimeError, match="inconsistent ownership"):
        repair()


def test_repair_never_overwrites_an_existing_conflicting_tenant(legacy_database):
    connection, schema = legacy_database
    seed_legacy_customer(connection)
    connection.execute(text("""INSERT INTO tenants (id, name, is_active, settings, created_at, updated_at)
        VALUES (2, 'Other business', true, '{}', now(), now())"""))
    connection.execute(text("ALTER TABLE customers ADD COLUMN tenant_id integer"))
    connection.execute(text("UPDATE customers SET tenant_id = 2 WHERE id = 20"))
    with pytest.raises(RuntimeError, match="inconsistent ownership"):
        repair()
    assert connection.scalar(text("SELECT tenant_id FROM customers WHERE id = 20")) == 2


def test_repair_restores_organization_uniqueness_and_preserves_tenant_keys(legacy_database):
    connection, schema = legacy_database
    for field in ("code", "name"):
        connection.execute(text(f"ALTER TABLE segments DROP CONSTRAINT segments_organization_id_{field}_key"))
    connection.execute(text("ALTER TABLE segments ADD COLUMN tenant_id integer REFERENCES tenants(id)"))
    for field in ("code", "name"):
        connection.execute(text(f"ALTER TABLE segments ADD CONSTRAINT legacy_segments_tenant_{field} UNIQUE (tenant_id, {field})"))
    repair()
    keys = {tuple(key["column_names"]) for key in inspect(connection).get_unique_constraints("segments", schema=schema)}
    assert {("organization_id", "code"), ("organization_id", "name"), ("tenant_id", "code"), ("tenant_id", "name")} <= keys
    repair()
