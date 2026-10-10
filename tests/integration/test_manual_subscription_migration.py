"""Explicit operator-only migration validation; excluded by --no-migrations."""
import pytest
from sqlalchemy import inspect, text

from tests.integration.test_tenant_migration import legacy_database, revision, seed_legacy_customer

pytestmark = pytest.mark.integration


def test_removal_preserves_subscription_invoice_history_and_rls(legacy_database):
    connection, schema = legacy_database
    seed_legacy_customer(connection)
    for name in ['e73a2109b001_repair_tenant_schema.py', 'f91c320ab002_saas_schema.py',
                 'f91c320ab003_force_tenant_rls.py', 'f91c320ab004_payment_gateway.py']:
        revision(name).upgrade()
    connection.execute(text("""INSERT INTO subscription_plans
        (id, name, provider_plan_id, amount_minor, currency, interval, total_cycles, entitlements, is_active, created_at, updated_at)
        VALUES ('preserved', 'Preserved plan', 'plan_History', 12000, 'INR', 'monthly', 12,
                '{"whatsapp_numbers": 2}', true, now(), now())"""))
    connection.execute(text("""INSERT INTO subscriptions
        (id, tenant_id, organization_id, plan_id, provider_subscription_id, status, current_start, current_end,
         cancel_at_period_end, created_at, updated_at)
        VALUES ('subscription-history', 1, 10, 'preserved', 'sub_History', 'active', now(), now() + interval '30 days', false, now(), now())"""))
    connection.execute(text("""INSERT INTO saas_invoices
        (id, tenant_id, organization_id, provider_payment_id, provider_invoice_id, amount_minor, currency,
         kind, status, buyer_snapshot, line_items, created_at, updated_at)
        VALUES ('invoice-history', 1, 10, 'pay_History', 'inv_History', 12000, 'INR', 'subscription', 'paid',
                '{"legal_name": "Preserved buyer"}', '[{"amount_minor": 12000}]', now(), now())"""))
    subscription = connection.execute(text("SELECT id, tenant_id, organization_id, plan_id, status, current_start, current_end FROM subscriptions")).one()
    tables = set(inspect(connection).get_table_names(schema=schema))
    migration = revision('f91c320ab005_manual_subscriptions.py')
    assert migration.down_revision == 'f91c320ab004'
    migration.upgrade()
    assert set(inspect(connection).get_table_names(schema=schema)) == tables - {'payment_gateway_settings', 'billing_events'}
    assert connection.execute(text("SELECT id, tenant_id, organization_id, plan_id, status, current_start, current_end FROM subscriptions")).one() == subscription
    invoice = connection.execute(text("SELECT payment_reference, invoice_reference, amount_minor, buyer_snapshot, line_items FROM saas_invoices")).one()
    assert tuple(invoice[:3]) == ('pay_History', 'inv_History', 12000)
    assert invoice.buyer_snapshot == {'legal_name': 'Preserved buyer'}
    assert invoice.line_items == [{'amount_minor': 12000}]
    assert connection.scalar(text("SELECT entitlements FROM subscription_plans WHERE id='preserved'")) == {'whatsapp_numbers': 2}
    for table in ['subscriptions', 'saas_invoices', 'customers']:
        assert connection.scalar(text("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid=to_regclass(:table)"), {'table': table})
    assert any(fk['name'] == 'fk_subscriptions_tenant_organization' for fk in inspect(connection).get_foreign_keys('subscriptions', schema=schema))
    with pytest.raises(RuntimeError, match='backup'):
        migration.downgrade()
