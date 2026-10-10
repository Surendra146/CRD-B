"""Force transaction-scoped row security on tenant data, including raw SQL."""
from alembic import op
import sqlalchemy as sa

revision = "f91c320ab003"
down_revision = "f91c320ab002"
branch_labels = None
depends_on = None

TABLES = ['generic_json_records', 'organizations', 'business_profiles', 'contact_consents', 'customers', 'saas_invoices', 'subscriptions', 'usage_entries', 'users', 'whatsapp_templates', 'audit_events', 'campaigns', 'consent_events', 'data_uploads', 'gmaps_extracted_leads', 'onboarding_requests', 'segments', 'whatsapp_auto_responders', 'whatsapp_bulk_jobs', 'whatsapp_connections', 'whatsapp_group_tasks', 'whatsapp_signup_attempts', 'campaign_outbox', 'data_upload_rows', 'message_records']


def upgrade():
    bind = op.get_bind()
    schema = bind.scalar(sa.text("SELECT current_schema()"))
    inspector = sa.inspect(bind)
    for table in TABLES:
        columns = {column["name"] for column in inspector.get_columns(table, schema=schema)}
        predicate = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::integer"
        if table == "organizations":
            predicate += " AND id = NULLIF(current_setting('app.organization_id', true), '')::integer"
        elif "organization_id" in columns:
            predicate += " AND organization_id = NULLIF(current_setting('app.organization_id', true), '')::integer"
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"CREATE POLICY hanuram_tenant_scope ON {table} USING ({predicate}) WITH CHECK ({predicate})"))
    predicate = "id = NULLIF(current_setting('app.tenant_id', true), '')::integer"
    op.execute(sa.text("ALTER TABLE tenants ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE tenants FORCE ROW LEVEL SECURITY"))
    op.execute(sa.text(f"CREATE POLICY hanuram_tenant_scope ON tenants USING ({predicate}) WITH CHECK ({predicate})"))


def downgrade():
    raise RuntimeError("Removing tenant row security requires a reviewed security rollback")
