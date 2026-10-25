"""Read-only production media audit preflight; never equates RLS silence with zero.

Uses process DATABASE_URL only. Does not import the application, load .env,
establish signed authority, query business rows, or access object storage.
The current authorization architecture has no all-tenant media inventory scope.
"""
import json
import os
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool


TABLES = ('whatsapp_templates', 'whatsapp_bulk_jobs')
ACCESS_REQUIRED = (
    'A security-owner-approved all-tenant reporting interface covering templates '
    'and campaign snapshots, with a restricted read-only login and explicit '
    'authorization under FORCE RLS. Existing runtime/control credentials and '
    'ordinary platform staff permissions do not supply this scope. Do not use '
    'superuser, BYPASSRLS, SET ROLE, row_security=off, job claims, or migration '
    'credentials as a workaround.'
)


def blocked(reason, **details):
    return {
        'status': 'blocked', 'scope': 'all_tenants_not_verified',
        'migration_required': None,
        'total_templates': None, 'referenced_media_assets': None,
        'unique_storage_keys': None, 'missing_metadata': None,
        'invalid_metadata': None,
        'reason': reason, 'authorized_access_required': ACCESS_REQUIRED,
        **details,
    }


def inspect(connection):
    # First SQL statement: database-enforced read-only snapshot. No application
    # imports/session listeners can establish authority or write context rows.
    connection.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
    connection.execute(text("SET LOCAL statement_timeout = '10s'"))
    connection.execute(text("SET LOCAL lock_timeout = '2s'"))
    role = connection.execute(text('''
        SELECT current_user = session_user AS direct_login,
               current_user IN ('hanuram_runtime', 'hanuram_control') AS app_login,
               rolsuper, rolbypassrls, rolcreaterole, rolcreatedb
        FROM pg_catalog.pg_roles WHERE rolname = current_user
    ''')).mappings().one()
    if not role['direct_login'] or not role['app_login'] or any(
            role[field] for field in ('rolsuper', 'rolbypassrls', 'rolcreaterole', 'rolcreatedb')):
        return blocked('Use a direct restricted existing runtime/control login; elevated or unreviewed logins are refused.')
    protections = {}
    for table in TABLES:
        row = connection.execute(text('''
            SELECT c.relrowsecurity, c.relforcerowsecurity,
                   c.relowner = (SELECT oid FROM pg_catalog.pg_roles WHERE rolname=current_user) AS owns_table
            FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relname=:table AND c.relkind='r'
        '''), {'table': table}).mappings().first()
        protections[table] = bool(row and row['relrowsecurity'] and row['relforcerowsecurity'] and not row['owns_table'])
    if not all(protections.values()):
        return blocked('Expected FORCE RLS tables or restricted ownership were not verified.', force_rls_verified=protections)
    return blocked(
        'The repository has no approved all-tenant media reporting scope. No tenant rows were queried; unknown counts are not zero.',
        force_rls_verified=protections,
    )


def main():
    engine = None
    try:
        # Deliberately do not read local .env: it normally targets development.
        raw = os.environ.get('DATABASE_URL')
        if os.environ.get('ENVIRONMENT', '').lower() != 'production' or not raw:
            report = blocked('Set process ENVIRONMENT=production and DATABASE_URL to the authorized production runtime login. Local .env is not loaded.')
        else:
            url = make_url(raw)
            if url.drivername == 'postgres':
                url = url.set(drivername='postgresql')
            if url.get_backend_name() != 'postgresql':
                raise ValueError('postgresql_required')
            engine = create_engine(url.set(drivername='postgresql+psycopg'), poolclass=NullPool,
                hide_parameters=True, echo=False, connect_args={'connect_timeout': 10})
            with engine.connect() as connection:
                report = inspect(connection)
                connection.rollback()
    except Exception:
        # Driver exceptions, SQL and DSNs may contain secrets: never stringify.
        report = blocked('Read-only connection/preflight failed. Check authorized production connectivity and role configuration privately.')
    finally:
        if engine is not None:
            engine.dispose()
    print(json.dumps(report, indent=2))
    return 2  # An incomplete audit must never be mistaken for success.


if __name__ == '__main__':
    sys.exit(main())
