"""SaaS schema, multiple sender support and composite tenant ownership keys."""
from alembic import op
import sqlalchemy as sa

revision = "f91c320ab002"
down_revision = "e73a2109b001"
branch_labels = None
depends_on = None

SCHEMA = [('billing_events',
  '\n'
  'CREATE TABLE billing_events (\n'
  '\tid VARCHAR(160) NOT NULL, \n'
  '\tbody_hash VARCHAR(64) NOT NULL, \n'
  '\tevent VARCHAR(80) NOT NULL, \n'
  '\tstatus VARCHAR(30) NOT NULL, \n'
  '\treceived_at TIMESTAMP WITH TIME ZONE NOT NULL, \n'
  '\tPRIMARY KEY (id)\n'
  ')\n'
  '\n',
  []),
 ('subscription_plans',
  '\n'
  'CREATE TABLE subscription_plans (\n'
  '\tid VARCHAR(80) NOT NULL, \n'
  '\tname VARCHAR(255) NOT NULL, \n'
  '\tprovider_plan_id VARCHAR(80) NOT NULL, \n'
  '\tamount_minor INTEGER NOT NULL, \n'
  '\tcurrency VARCHAR(3) NOT NULL, \n'
  '\tinterval VARCHAR(30) NOT NULL, \n'
  '\ttotal_cycles INTEGER NOT NULL, \n'
  '\tentitlements JSONB NOT NULL, \n'
  '\tis_active BOOLEAN NOT NULL, \n'
  '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
  '\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tCHECK (amount_minor > 0), \n'
  '\tCHECK (total_cycles > 0), \n'
  '\tUNIQUE (provider_plan_id)\n'
  ')\n'
  '\n',
  []),
 ('business_profiles',
  '\n'
  'CREATE TABLE business_profiles (\n'
  '\tid SERIAL NOT NULL, \n'
  '\ttenant_id INTEGER NOT NULL, \n'
  '\torganization_id INTEGER NOT NULL, \n'
  '\tlegal_name VARCHAR(255) NOT NULL, \n'
  '\tbilling_email VARCHAR(255), \n'
  '\tphone VARCHAR(60), \n'
  '\taddress JSONB NOT NULL, \n'
  '\ttax_id VARCHAR(40), \n'
  '\twebsite VARCHAR(500), \n'
  '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
  '\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n'
  '\tUNIQUE (organization_id), \n'
  '\tFOREIGN KEY(organization_id) REFERENCES organizations (id)\n'
  ')\n'
  '\n',
  ['CREATE INDEX ix_business_profiles_tenant_id ON business_profiles (tenant_id)']),
 ('contact_consents',
  '\n'
  'CREATE TABLE contact_consents (\n'
  '\tid SERIAL NOT NULL, \n'
  '\ttenant_id INTEGER NOT NULL, \n'
  '\torganization_id INTEGER NOT NULL, \n'
  '\tphone VARCHAR(20) NOT NULL, \n'
  '\topted_in BOOLEAN NOT NULL, \n'
  '\tsource VARCHAR(80), \n'
  '\tevidence TEXT, \n'
  '\tlast_inbound_at TIMESTAMP WITH TIME ZONE, \n'
  '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
  '\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tUNIQUE (tenant_id, organization_id, phone), \n'
  '\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n'
  '\tFOREIGN KEY(organization_id) REFERENCES organizations (id)\n'
  ')\n'
  '\n',
  ['CREATE INDEX ix_contact_consents_tenant_id ON contact_consents (tenant_id)']),
 ('saas_invoices',
  '\n'
  'CREATE TABLE saas_invoices (\n'
  '\tid VARCHAR(80) NOT NULL, \n'
  '\ttenant_id INTEGER NOT NULL, \n'
  '\torganization_id INTEGER NOT NULL, \n'
  '\tprovider_payment_id VARCHAR(120) NOT NULL, \n'
  '\tprovider_invoice_id VARCHAR(120), \n'
  '\tamount_minor INTEGER NOT NULL, \n'
  '\tcurrency VARCHAR(3) NOT NULL, \n'
  '\tkind VARCHAR(30) NOT NULL, \n'
  '\tstatus VARCHAR(30) NOT NULL, \n'
  '\tbuyer_snapshot JSONB NOT NULL, \n'
  '\tline_items JSONB NOT NULL, \n'
  '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
  '\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tCHECK (amount_minor >= 0), \n'
  '\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n'
  '\tFOREIGN KEY(organization_id) REFERENCES organizations (id), \n'
  '\tUNIQUE (provider_payment_id)\n'
  ')\n'
  '\n',
  ['CREATE INDEX ix_saas_invoices_tenant_id ON saas_invoices (tenant_id)']),
 ('subscriptions',
  '\n'
  'CREATE TABLE subscriptions (\n'
  '\tid VARCHAR(80) NOT NULL, \n'
  '\ttenant_id INTEGER NOT NULL, \n'
  '\torganization_id INTEGER NOT NULL, \n'
  '\tplan_id VARCHAR(80) NOT NULL, \n'
  '\tprovider_subscription_id VARCHAR(80), \n'
  '\tstatus VARCHAR(40) NOT NULL, \n'
  '\tcurrent_start TIMESTAMP WITH TIME ZONE, \n'
  '\tcurrent_end TIMESTAMP WITH TIME ZONE, \n'
  '\tprovider_updated_at TIMESTAMP WITH TIME ZONE, \n'
  '\tcancel_at_period_end BOOLEAN NOT NULL, \n'
  '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
  '\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n'
  '\tUNIQUE (organization_id), \n'
  '\tFOREIGN KEY(organization_id) REFERENCES organizations (id), \n'
  '\tFOREIGN KEY(plan_id) REFERENCES subscription_plans (id), \n'
  '\tUNIQUE (provider_subscription_id)\n'
  ')\n'
  '\n',
  ['CREATE INDEX ix_subscriptions_tenant_id ON subscriptions (tenant_id)']),
 ('usage_entries',
  '\n'
  'CREATE TABLE usage_entries (\n'
  '\tid VARCHAR(80) NOT NULL, \n'
  '\ttenant_id INTEGER NOT NULL, \n'
  '\torganization_id INTEGER NOT NULL, \n'
  '\texternal_reference VARCHAR(160) NOT NULL, \n'
  '\tcategory VARCHAR(40) NOT NULL, \n'
  '\tquantity INTEGER NOT NULL, \n'
  '\tamount_minor INTEGER, \n'
  '\tcurrency VARCHAR(3), \n'
  '\tprovider VARCHAR(80) NOT NULL, \n'
  '\tperiod VARCHAR(80), \n'
  '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
  '\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tUNIQUE (tenant_id, external_reference), \n'
  '\tCHECK (amount_minor IS NULL OR amount_minor >= 0), \n'
  '\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n'
  '\tFOREIGN KEY(organization_id) REFERENCES organizations (id)\n'
  ')\n'
  '\n',
  ['CREATE INDEX ix_usage_entries_tenant_id ON usage_entries (tenant_id)']),
 ('audit_events',
  '\n'
  'CREATE TABLE audit_events (\n'
  '\tid VARCHAR(80) NOT NULL, \n'
  '\ttenant_id INTEGER NOT NULL, \n'
  '\torganization_id INTEGER NOT NULL, \n'
  '\tactor_id INTEGER, \n'
  '\taction VARCHAR(120) NOT NULL, \n'
  '\tresource_id VARCHAR(160), \n'
  '\tdetails JSONB NOT NULL, \n'
  '\toccurred_at TIMESTAMP WITH TIME ZONE NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n'
  '\tFOREIGN KEY(organization_id) REFERENCES organizations (id), \n'
  '\tFOREIGN KEY(actor_id) REFERENCES users (id)\n'
  ')\n'
  '\n',
  ['CREATE INDEX ix_audit_events_tenant_id ON audit_events (tenant_id)']),
 ('consent_events',
  '\n'
  'CREATE TABLE consent_events (\n'
  '\tid VARCHAR(80) NOT NULL, \n'
  '\ttenant_id INTEGER NOT NULL, \n'
  '\torganization_id INTEGER NOT NULL, \n'
  '\tphone VARCHAR(20) NOT NULL, \n'
  '\topted_in BOOLEAN NOT NULL, \n'
  '\tsource VARCHAR(80) NOT NULL, \n'
  '\tevidence TEXT, \n'
  '\tactor_id INTEGER, \n'
  '\toccurred_at TIMESTAMP WITH TIME ZONE NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n'
  '\tFOREIGN KEY(organization_id) REFERENCES organizations (id), \n'
  '\tFOREIGN KEY(actor_id) REFERENCES users (id)\n'
  ')\n'
  '\n',
  ['CREATE INDEX ix_consent_events_tenant_id ON consent_events (tenant_id)']),
 ('onboarding_requests',
  '\n'
  'CREATE TABLE onboarding_requests (\n'
  '\tid VARCHAR(80) NOT NULL, \n'
  '\ttenant_id INTEGER NOT NULL, \n'
  '\torganization_id INTEGER NOT NULL, \n'
  '\tphone VARCHAR(30) NOT NULL, \n'
  '\tbusiness_name VARCHAR(255) NOT NULL, \n'
  '\tstatus VARCHAR(40) NOT NULL, \n'
  '\tcustomer_message TEXT, \n'
  '\tprovider_reference VARCHAR(255), \n'
  '\tcreated_by INTEGER NOT NULL, \n'
  '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
  '\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n'
  '\tFOREIGN KEY(organization_id) REFERENCES organizations (id), \n'
  '\tFOREIGN KEY(created_by) REFERENCES users (id)\n'
  ')\n'
  '\n',
  ['CREATE INDEX ix_onboarding_requests_tenant_id ON onboarding_requests (tenant_id)']),
 ('platform_staff',
  '\n'
  'CREATE TABLE platform_staff (\n'
  '\tuser_id INTEGER NOT NULL, \n'
  '\tis_active BOOLEAN NOT NULL, \n'
  '\tpermissions JSONB NOT NULL, \n'
  '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
  '\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
  '\tPRIMARY KEY (user_id), \n'
  '\tFOREIGN KEY(user_id) REFERENCES users (id)\n'
  ')\n'
  '\n',
  []),
 ('campaign_outbox',
  '\n'
  'CREATE TABLE campaign_outbox (\n'
  '\tid VARCHAR(80) NOT NULL, \n'
  '\ttenant_id INTEGER NOT NULL, \n'
  '\torganization_id INTEGER NOT NULL, \n'
  '\tbulk_job_id INTEGER NOT NULL, \n'
  '\tstatus VARCHAR(30) NOT NULL, \n'
  '\tlast_attempt_at TIMESTAMP WITH TIME ZONE, \n'
  '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
  '\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n'
  '\tFOREIGN KEY(organization_id) REFERENCES organizations (id), \n'
  '\tUNIQUE (bulk_job_id), \n'
  '\tFOREIGN KEY(bulk_job_id) REFERENCES whatsapp_bulk_jobs (id)\n'
  ')\n'
  '\n',
  ['CREATE INDEX ix_campaign_outbox_tenant_id ON campaign_outbox (tenant_id)']),
 ('message_records',
  '\n'
  'CREATE TABLE message_records (\n'
  '\tid VARCHAR(80) NOT NULL, \n'
  '\ttenant_id INTEGER NOT NULL, \n'
  '\torganization_id INTEGER NOT NULL, \n'
  '\tprovider_message_id VARCHAR(255), \n'
  '\tsender_phone_id VARCHAR(80) NOT NULL, \n'
  '\trecipient VARCHAR(20) NOT NULL, \n'
  '\tstatus VARCHAR(40) NOT NULL, \n'
  '\tstatus_timestamp INTEGER NOT NULL, \n'
  '\tbulk_job_id INTEGER, \n'
  '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
  '\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n'
  '\tFOREIGN KEY(organization_id) REFERENCES organizations (id), \n'
  '\tUNIQUE (provider_message_id), \n'
  '\tFOREIGN KEY(bulk_job_id) REFERENCES whatsapp_bulk_jobs (id)\n'
  ')\n'
  '\n',
  ['CREATE INDEX ix_message_records_tenant_id ON message_records (tenant_id)'])]


def upgrade():
    bind = op.get_bind()
    schema = bind.scalar(sa.text("SELECT current_schema()"))
    tables = set(sa.inspect(bind).get_table_names(schema=schema))
    for table, ddl, indexes in SCHEMA:
        if table in tables:
            raise RuntimeError(f"Unexpected existing SaaS table {table}; reconcile migration history")
        op.execute(sa.text(ddl))
        for index in indexes:
            op.execute(sa.text(index))
    # Populate separate profiles for existing businesses without changing their IDs.
    op.execute(sa.text("""INSERT INTO business_profiles
        (tenant_id, organization_id, legal_name, address, created_at, updated_at)
        SELECT tenant_id, id, name, '{}'::jsonb, now(), now() FROM organizations
        WHERE tenant_id IS NOT NULL"""))
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("whatsapp_connections", schema=schema)}
    if "is_default" not in columns:
        op.add_column("whatsapp_connections", sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()))
    for constraint in inspector.get_unique_constraints("whatsapp_connections", schema=schema):
        if constraint["column_names"] == ["organization_id"]:
            op.drop_constraint(constraint["name"], "whatsapp_connections", type_="unique")
    op.execute(sa.text("""UPDATE whatsapp_connections AS connection SET is_default = true
        WHERE connection.id IN (SELECT min(id) FROM whatsapp_connections GROUP BY organization_id)
          AND NOT EXISTS (SELECT 1 FROM whatsapp_connections AS other
                          WHERE other.organization_id = connection.organization_id AND other.is_default)"""))
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("whatsapp_connections", schema=schema)}
    if "uq_whatsapp_default_sender" not in indexes:
        op.create_index("uq_whatsapp_default_sender", "whatsapp_connections", ["organization_id"], unique=True, postgresql_where=sa.text("is_default"))
    op.create_unique_constraint("uq_organizations_tenant_id", "organizations", ["tenant_id", "id"])
    for table in ['generic_json_records', 'organizations', 'business_profiles', 'contact_consents', 'customers', 'saas_invoices', 'subscriptions', 'usage_entries', 'users', 'whatsapp_templates', 'audit_events', 'campaigns', 'consent_events', 'data_uploads', 'gmaps_extracted_leads', 'onboarding_requests', 'segments', 'whatsapp_auto_responders', 'whatsapp_bulk_jobs', 'whatsapp_connections', 'whatsapp_group_tasks', 'whatsapp_signup_attempts', 'campaign_outbox', 'data_upload_rows', 'message_records']:
        columns = {column["name"] for column in sa.inspect(bind).get_columns(table, schema=schema)}
        if "organization_id" not in columns or table == "organizations":
            continue
        # Existing inconsistent rows cause constraint validation to fail; never move rows.
        op.create_foreign_key(f"fk_{table}_tenant_organization", table, "organizations", ["tenant_id", "organization_id"], ["tenant_id", "id"])
    for table in ("users", "customers", "data_uploads", "whatsapp_templates", "whatsapp_bulk_jobs"):
        op.create_unique_constraint(f"uq_{table}_id_tenant_org", table, ["id", "tenant_id", "organization_id"])
    for table, column, target in (
        ("campaigns", "template_id", "whatsapp_templates"),
        ("campaigns", "created_by", "users"),
        ("data_upload_rows", "upload_id", "data_uploads"),
        ("whatsapp_connections", "connected_by", "users"),
        ("whatsapp_signup_attempts", "user_id", "users"),
        ("campaign_outbox", "bulk_job_id", "whatsapp_bulk_jobs"),
        ("message_records", "bulk_job_id", "whatsapp_bulk_jobs"),
        ("gmaps_extracted_leads", "customer_id", "customers"),
    ):
        op.create_foreign_key(f"fk_{table}_{column}_scope", table, target, [column, "tenant_id", "organization_id"], ["id", "tenant_id", "organization_id"])
    op.execute(sa.text("""CREATE FUNCTION hanuram_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'This record is append-only'; END; $$"""))
    for table in ("audit_events", "consent_events", "usage_entries"):
        op.execute(sa.text(f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION hanuram_append_only()"))


def downgrade():
    raise RuntimeError("SaaS migration is forward-only; use a reviewed backup to avoid dropping billing and customer records")
