"""Frozen historical gateway migration coverage; run only by explicit operator request."""
import pytest
from tests.integration.test_tenant_migration import legacy_database

pytestmark = pytest.mark.integration


def test_gateway_migration_preserves_existing_tables_and_round_trips(legacy_database):
    from sqlalchemy import inspect, text
    from tests.integration.test_tenant_migration import revision
    connection, schema = legacy_database
    before = set(inspect(connection).get_table_names(schema=schema))
    migration = revision("f91c320ab004_payment_gateway.py")
    migration.upgrade()
    assert set(inspect(connection).get_table_names(schema=schema)) == before | {"payment_gateway_settings"}
    connection.execute(text("INSERT INTO payment_gateway_settings (id, enabled, created_at, updated_at) VALUES ('default', false, now(), now())"))
    assert connection.scalar(text("SELECT enabled FROM payment_gateway_settings WHERE id = 'default'")) is False
    migration.downgrade()
    assert set(inspect(connection).get_table_names(schema=schema)) == before
