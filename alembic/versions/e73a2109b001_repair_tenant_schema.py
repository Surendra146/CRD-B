"""Repair legacy tenant columns and missing marketing tables without replacing data.

This frozen revision does not import application model definitions. Inconsistent
ownership aborts the transaction; operators must investigate, never guess tenants.
"""
from alembic import op
import sqlalchemy as sa

revision = "e73a2109b001"
down_revision = "d24bf074d970"
branch_labels = None
depends_on = None

OWNED_TABLES = (
    "customers", "campaigns", "data_uploads", "data_upload_rows",
    "segments", "whatsapp_templates", "generic_json_records",
)

MARKETING_SCHEMA = [('whatsapp_bulk_jobs',
  '\n'
  'CREATE TABLE whatsapp_bulk_jobs (\n'
  '\tid SERIAL NOT NULL, \n'
  '\ttenant_id INTEGER NOT NULL, \n'
  '\torganization_id INTEGER NOT NULL, \n'
  '\ttenant_code VARCHAR(80), \n'
  '\ttitle VARCHAR(255) NOT NULL, \n'
  '\taudience_type VARCHAR(80) NOT NULL, \n'
  '\taudience_payload JSONB NOT NULL, \n'
  '\tmessage_template TEXT NOT NULL, \n'
  '\tbuttons JSONB NOT NULL, \n'
  '\tmedia_files JSONB NOT NULL, \n'
  '\tbatch_delay_seconds INTEGER NOT NULL, \n'
  '\tscheduled_at TIMESTAMP WITHOUT TIME ZONE, \n'
  '\tstatus VARCHAR(80) NOT NULL, \n'
  '\tstats JSONB NOT NULL, \n'
  '\trecipients_summary JSONB NOT NULL, \n'
  '\tcreated_by INTEGER, \n'
  '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
  '\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n'
  '\tFOREIGN KEY(organization_id) REFERENCES organizations (id), \n'
  '\tFOREIGN KEY(created_by) REFERENCES users (id)\n'
  ')\n'
  '\n',
  ['CREATE INDEX ix_whatsapp_bulk_jobs_organization_id ON whatsapp_bulk_jobs (organization_id)',
   'CREATE INDEX ix_whatsapp_bulk_jobs_status ON whatsapp_bulk_jobs (status)',
   'CREATE INDEX ix_whatsapp_bulk_jobs_tenant_code ON whatsapp_bulk_jobs (tenant_code)',
   'CREATE INDEX ix_whatsapp_bulk_jobs_tenant_id ON whatsapp_bulk_jobs (tenant_id)',
   'CREATE INDEX ix_whatsapp_bulk_jobs_tenant_org ON whatsapp_bulk_jobs (tenant_id, '
   'organization_id)']),
 ('whatsapp_auto_responders',
  '\n'
  'CREATE TABLE whatsapp_auto_responders (\n'
  '\tid SERIAL NOT NULL, \n'
  '\ttenant_id INTEGER NOT NULL, \n'
  '\torganization_id INTEGER NOT NULL, \n'
  '\ttenant_code VARCHAR(80), \n'
  '\tname VARCHAR(255) NOT NULL, \n'
  '\ttrigger_type VARCHAR(80) NOT NULL, \n'
  '\tkeywords JSONB NOT NULL, \n'
  '\tresponse_message TEXT NOT NULL, \n'
  '\tbuttons JSONB NOT NULL, \n'
  '\tmedia_files JSONB NOT NULL, \n'
  '\tis_active BOOLEAN NOT NULL, \n'
  '\tpriority INTEGER NOT NULL, \n'
  '\tmatch_count INTEGER NOT NULL, \n'
  '\tlast_triggered_at TIMESTAMP WITHOUT TIME ZONE, \n'
  '\tcreated_by INTEGER, \n'
  '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
  '\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n'
  '\tFOREIGN KEY(organization_id) REFERENCES organizations (id), \n'
  '\tFOREIGN KEY(created_by) REFERENCES users (id)\n'
  ')\n'
  '\n',
  ['CREATE INDEX ix_whatsapp_auto_responders_organization_id ON whatsapp_auto_responders '
   '(organization_id)',
   'CREATE INDEX ix_whatsapp_auto_responders_tenant_code ON whatsapp_auto_responders (tenant_code)',
   'CREATE INDEX ix_whatsapp_auto_responders_tenant_id ON whatsapp_auto_responders (tenant_id)',
   'CREATE INDEX ix_whatsapp_auto_responders_tenant_org ON whatsapp_auto_responders (tenant_id, '
   'organization_id)']),
 ('gmaps_extracted_leads',
  '\n'
  'CREATE TABLE gmaps_extracted_leads (\n'
  '\tid SERIAL NOT NULL, \n'
  '\ttenant_id INTEGER NOT NULL, \n'
  '\torganization_id INTEGER NOT NULL, \n'
  '\ttenant_code VARCHAR(80), \n'
  '\tsearch_query VARCHAR(255) NOT NULL, \n'
  '\tlocation VARCHAR(255) NOT NULL, \n'
  '\tbusiness_name VARCHAR(255) NOT NULL, \n'
  '\tphone VARCHAR(80), \n'
  '\tcategory VARCHAR(120), \n'
  '\trating VARCHAR(40), \n'
  '\treviews_count INTEGER NOT NULL, \n'
  '\taddress TEXT, \n'
  '\twebsite VARCHAR(255), \n'
  '\tis_imported BOOLEAN NOT NULL, \n'
  '\tcustomer_id INTEGER, \n'
  '\traw_data JSONB NOT NULL, \n'
  '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
  '\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n'
  '\tFOREIGN KEY(organization_id) REFERENCES organizations (id), \n'
  '\tFOREIGN KEY(customer_id) REFERENCES customers (id)\n'
  ')\n'
  '\n',
  ['CREATE INDEX ix_gmaps_extracted_leads_organization_id ON gmaps_extracted_leads '
   '(organization_id)',
   'CREATE INDEX ix_gmaps_extracted_leads_phone ON gmaps_extracted_leads (phone)',
   'CREATE INDEX ix_gmaps_extracted_leads_search_query ON gmaps_extracted_leads (search_query)',
   'CREATE INDEX ix_gmaps_extracted_leads_tenant_code ON gmaps_extracted_leads (tenant_code)',
   'CREATE INDEX ix_gmaps_extracted_leads_tenant_id ON gmaps_extracted_leads (tenant_id)',
   'CREATE INDEX ix_gmaps_leads_tenant_org ON gmaps_extracted_leads (tenant_id, organization_id)']),
 ('whatsapp_group_tasks',
  '\n'
  'CREATE TABLE whatsapp_group_tasks (\n'
  '\tid SERIAL NOT NULL, \n'
  '\ttenant_id INTEGER NOT NULL, \n'
  '\torganization_id INTEGER NOT NULL, \n'
  '\ttenant_code VARCHAR(80), \n'
  '\ttask_type VARCHAR(80) NOT NULL, \n'
  '\ttitle VARCHAR(255) NOT NULL, \n'
  '\tgroup_name VARCHAR(255), \n'
  '\textracted_count INTEGER NOT NULL, \n'
  '\tstatus VARCHAR(80) NOT NULL, \n'
  '\tdetails JSONB NOT NULL, \n'
  '\tcreated_by INTEGER, \n'
  '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
  '\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
  '\tPRIMARY KEY (id), \n'
  '\tFOREIGN KEY(tenant_id) REFERENCES tenants (id), \n'
  '\tFOREIGN KEY(organization_id) REFERENCES organizations (id), \n'
  '\tFOREIGN KEY(created_by) REFERENCES users (id)\n'
  ')\n'
  '\n',
  ['CREATE INDEX ix_whatsapp_group_tasks_organization_id ON whatsapp_group_tasks (organization_id)',
   'CREATE INDEX ix_whatsapp_group_tasks_tenant_code ON whatsapp_group_tasks (tenant_code)',
   'CREATE INDEX ix_whatsapp_group_tasks_tenant_id ON whatsapp_group_tasks (tenant_id)',
   'CREATE INDEX ix_whatsapp_group_tasks_tenant_org ON whatsapp_group_tasks (tenant_id, '
   'organization_id)'])]


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    schema = bind.scalar(sa.text("SELECT current_schema()"))
    tables = set(inspector.get_table_names(schema=schema))
    for table in OWNED_TABLES:
        if table not in tables:
            raise RuntimeError(f"Missing baseline table {table}; verify Alembic history before repair")
        columns = {column["name"] for column in inspector.get_columns(table, schema=schema)}
        if "tenant_id" not in columns:
            op.add_column(table, sa.Column("tenant_id", sa.Integer(), nullable=True))
        # Existing tenant values are immutable; only fill previously absent ownership.
        bind.execute(sa.text(f"""UPDATE {table} AS record SET tenant_id = organization.tenant_id
            FROM organizations AS organization
            WHERE record.organization_id = organization.id AND record.tenant_id IS NULL
              AND organization.tenant_id IS NOT NULL"""))
        inconsistent = bind.scalar(sa.text(f"""SELECT count(*) FROM {table} AS record
            LEFT JOIN organizations AS organization ON organization.id = record.organization_id
            LEFT JOIN tenants AS tenant ON tenant.id = record.tenant_id
            WHERE (record.organization_id IS NOT NULL AND
                   (organization.id IS NULL OR organization.tenant_id IS NULL OR record.tenant_id IS DISTINCT FROM organization.tenant_id))
               OR (record.tenant_id IS NOT NULL AND tenant.id IS NULL)"""))
        if inconsistent:
            raise RuntimeError(f"Tenant repair stopped: {table} has {inconsistent} inconsistent ownership rows")
        if table != "generic_json_records":
            unresolved = bind.scalar(sa.text(f"SELECT count(*) FROM {table} WHERE tenant_id IS NULL"))
            if unresolved:
                raise RuntimeError(f"Tenant repair stopped: {table} has {unresolved} unresolved tenant rows")
            op.alter_column(table, "tenant_id", existing_type=sa.Integer(), nullable=False)
        foreign_keys = sa.inspect(bind).get_foreign_keys(table, schema=schema)
        if not any(fk["constrained_columns"] == ["tenant_id"] and fk["referred_table"] == "tenants" for fk in foreign_keys):
            op.create_foreign_key(f"fk_{table}_tenant_id", table, "tenants", ["tenant_id"], ["id"])
        indexes = {index["name"] for index in sa.inspect(bind).get_indexes(table, schema=schema)}
        index_name = f"ix_{table}_tenant_id"
        if index_name not in indexes:
            op.create_index(index_name, table, ["tenant_id"])
    # Reviewed legacy deployments replaced organization uniqueness with tenant
    # uniqueness. Restore the historical keys without dropping the tenant keys.
    unique_keys = {tuple(key["column_names"]) for key in sa.inspect(bind).get_unique_constraints("segments", schema=schema)}
    for field in ("code", "name"):
        columns = ("organization_id", field)
        if columns not in unique_keys:
            duplicates = bind.scalar(sa.text(f"""SELECT count(*) FROM (
                SELECT organization_id, {field} FROM segments
                WHERE organization_id IS NOT NULL AND {field} IS NOT NULL
                GROUP BY organization_id, {field} HAVING count(*) > 1
            ) AS duplicate_groups"""))
            if duplicates:
                raise RuntimeError(f"Segment reconciliation stopped: duplicate organization/{field} pairs")
            op.create_unique_constraint(f"uq_segments_organization_{field}", "segments", list(columns))
    # Upload row scope must agree with its parent, not merely a valid organization.
    inconsistent_uploads = bind.scalar(sa.text("""SELECT count(*) FROM data_upload_rows AS row
        JOIN data_uploads AS upload ON upload.id = row.upload_id
        WHERE row.tenant_id != upload.tenant_id OR row.organization_id != upload.organization_id"""))
    if inconsistent_uploads:
        raise RuntimeError("Tenant repair stopped: upload rows disagree with parent ownership")
    for table, ddl, indexes in MARKETING_SCHEMA:
        if table not in tables:
            op.execute(sa.text(ddl))
            for ddl_index in indexes:
                op.execute(sa.text(ddl_index))


def downgrade():
    # Removing tenant IDs or marketing tables would lose customer data/security scope.
    raise RuntimeError("Tenant schema repair is forward-only; restore a reviewed backup instead of dropping customer data")
