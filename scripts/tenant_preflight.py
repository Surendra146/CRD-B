"""Read-only schema/ownership report. Never prints credentials or customer records."""
import json
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

TABLES = ("customers", "campaigns", "data_uploads", "data_upload_rows", "segments", "whatsapp_templates", "generic_json_records")
MARKETING = ("whatsapp_bulk_jobs", "whatsapp_auto_responders", "gmaps_extracted_leads", "whatsapp_group_tasks")


def report(connection):
    connection.execute(text("SET TRANSACTION READ ONLY"))
    inspector = inspect(connection)
    schema = connection.scalar(text("SELECT current_schema()"))
    tables = set(inspector.get_table_names(schema=schema))
    result = {"schema": schema, "tables": {}, "missing_marketing_tables": sorted(set(MARKETING) - tables)}
    if "alembic_version" in tables:
        result["alembic_revisions"] = list(connection.scalars(text("SELECT version_num FROM alembic_version")))
    else:
        result["alembic_revisions"] = []
    for table in TABLES:
        if table not in tables:
            result["tables"][table] = {"missing_table": True}
            continue
        columns = {column["name"] for column in inspector.get_columns(table, schema=schema)}
        details = {"row_count": connection.scalar(text(f"SELECT count(*) FROM {table}")), "missing_tenant_column": "tenant_id" not in columns}
        if "organizations" in tables:
            details["unresolved_organization_rows"] = connection.scalar(text(f"""SELECT count(*) FROM {table} AS record
                LEFT JOIN organizations AS organization ON organization.id = record.organization_id
                WHERE record.organization_id IS NOT NULL AND (organization.id IS NULL OR organization.tenant_id IS NULL)"""))
            if "tenant_id" in columns:
                details["conflicting_tenant_rows"] = connection.scalar(text(f"""SELECT count(*) FROM {table} AS record
                    JOIN organizations AS organization ON organization.id = record.organization_id
                    WHERE record.tenant_id IS NOT NULL AND record.tenant_id IS DISTINCT FROM organization.tenant_id"""))
                details["null_tenant_rows"] = connection.scalar(text(f"SELECT count(*) FROM {table} WHERE tenant_id IS NULL"))
        result["tables"][table] = details
    return result


def main():
    load_dotenv()
    raw = os.getenv("DATABASE_URL")
    if not raw:
        raise SystemExit("DATABASE_URL is required")
    raw = raw.replace("postgres://", "postgresql://", 1)
    url = make_url(raw)
    if url.get_backend_name() != "postgresql":
        raise SystemExit("PostgreSQL is required")
    engine = create_engine(url.set(drivername="postgresql+psycopg"))
    stage = "connecting to PostgreSQL"
    try:
        with engine.begin() as connection:
            connection.execute(text("SELECT 1"))
            stage = "checking the restored schema"
            result = report(connection)
        print(json.dumps(result, indent=2))
    except Exception as error:
        # Never print exception text: drivers can include credentials and SQL data.
        original = getattr(error, "orig", None)
        code = getattr(original, "sqlstate", None)
        explanations = {
            "28P01": "PostgreSQL rejected the password. Check the local login credentials.",
            "28000": "PostgreSQL rejected the login. Check role and authentication configuration.",
            "3D000": "The configured database does not exist. Confirm the restored database name.",
            "42501": "The database role lacks permission to inspect the restored tables.",
            "42P01": "A table required by the schema check is missing or outside the search path.",
            "42703": "A column required by the schema check is missing. The restore may use an older schema.",
            "25006": "The database rejected a command in the read-only transaction.",
        }
        hint = explanations.get(code, "Check PostgreSQL service, host, port, SSL settings and the database URL. If connectivity works, inspect the restored schema.")
        safe_code = code if isinstance(code, str) and len(code) == 5 and code.isalnum() else "unavailable"
        raise SystemExit(f"Preflight failed while {stage}. Error type: {type(error).__name__}; SQLSTATE: {safe_code}. {hint}") from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
