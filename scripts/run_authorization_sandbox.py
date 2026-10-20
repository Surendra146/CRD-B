"""Start a disposable PostgreSQL cluster; never connect to existing databases.

Uses installed PostgreSQL binaries and generated in-memory credentials. Application
migrations run as a NOSUPERUSER NOBYPASSRLS operator. The cluster bootstrap account
is used only to create that operator and the empty disposable database/logins.
"""
import argparse
import importlib.util
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile

import psycopg
from psycopg import sql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

ROOT=Path(__file__).resolve().parents[1]


def run(argv, **kwargs):
    capture='stdout' not in kwargs
    if capture:
        kwargs.update(stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    result=subprocess.run([str(arg) for arg in argv],
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0, **kwargs)
    if capture and result.stdout:
        print(result.stdout,flush=True)
    result.check_returncode()
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--postgres-bin', default=r'C:\Program Files\PostgreSQL\18\bin')
    parser.add_argument('--legacy-tests', action='store_true',help='Also run existing suite in this same disposable cluster')
    args=parser.parse_args()
    binpath=Path(args.postgres_bin)
    suffix='.exe' if os.name=='nt' else ''
    for executable in ('initdb','pg_ctl'):
        if not (binpath/(executable+suffix)).is_file():
            parser.error('PostgreSQL initdb/pg_ctl binaries are required; no existing server will be used')
    with socket.socket() as reserve:
        reserve.bind(('127.0.0.1',0)); port=reserve.getsockname()[1]
    passwords={role:secrets.token_urlsafe(32) for role in ('sandbox_bootstrap','sandbox_operator','hanuram_runtime','hanuram_control')}
    # The production-name guard is exercised unchanged in this isolated cluster.
    database='hanuram_production_ii23'
    marker=secrets.token_hex(32)
    with tempfile.TemporaryDirectory(prefix='hanuram_authorization_') as temp:
        folder=Path(temp); data=folder/'cluster'; pwfile=folder/'bootstrap-password'
        pwfile.write_text(passwords['sandbox_bootstrap'])
        started=False
        try:
            run([binpath/('initdb'+suffix),'-D',data,'-U','sandbox_bootstrap','--auth=scram-sha-256','--pwfile',pwfile,'--encoding=UTF8','--locale=C'],stdout=subprocess.DEVNULL)
            pwfile.unlink()
            run([binpath/('pg_ctl'+suffix),'-D',data,'-l',folder/'postgres.log','-o',f"-p {port} -h 127.0.0.1 -F",'-w','start'],stdout=subprocess.DEVNULL)
            started=True
            print('Disposable PostgreSQL started; existing databases and services are not used.',flush=True)
            with psycopg.connect(host='127.0.0.1',port=port,dbname='postgres',user='sandbox_bootstrap',password=passwords['sandbox_bootstrap'],autocommit=True) as bootstrap:
                for role in ('sandbox_operator','hanuram_runtime','hanuram_control'):
                    attributes=sql.SQL('LOGIN NOSUPERUSER NOBYPASSRLS CREATEROLE CREATEDB') if role=='sandbox_operator' else sql.SQL('LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB')
                    bootstrap.execute(sql.SQL('CREATE ROLE {} {} PASSWORD {}').format(sql.Identifier(role),attributes,sql.Literal(passwords[role])))
                bootstrap.execute(sql.SQL('CREATE DATABASE {} OWNER sandbox_operator').format(sql.Identifier(database)))
            urls={role:URL.create('postgresql+psycopg',username=role,password=passwords[role],host='127.0.0.1',port=port,database=database).render_as_string(hide_password=False)
                  for role in ('sandbox_operator','hanuram_runtime','hanuram_control')}
            env={**os.environ,'ENVIRONMENT':'test','REQUIRE_RLS':'true','AUTO_CREATE_TABLES':'false',
                 'DATABASE_URL':urls['hanuram_runtime'],'CONTROL_DATABASE_URL':urls['hanuram_control'],
                 'MIGRATION_DATABASE_URL':urls['sandbox_operator'],'AUTHORIZATION_SANDBOX_URL':urls['sandbox_operator'],
                 'AUTHORIZATION_SANDBOX_MARKER':marker,'JWT_SECRET':secrets.token_urlsafe(40),
                 'META_APP_SECRET':secrets.token_urlsafe(40),'WHATSAPP_VERIFY_TOKEN':secrets.token_urlsafe(40),
                 'WHATSAPP_TOKEN_ENCRYPTION_KEY':secrets.token_urlsafe(40),'ENABLE_SOCKET_PROGRESS':'false',
                 'ENABLE_REDIS_PROGRESS':'false','CAMPAIGN_TRANSPORT':'database','ENFORCE_SUBSCRIPTION':'true'}
            for kind in ('IDENTITY','STAFF','JOBS'):
                env['DATABASE_AUTH_'+kind+'_KEY']=secrets.token_urlsafe(48)
            operator=create_engine(urls['sandbox_operator'],hide_parameters=True)
            # Negative cases run only on the cluster initialized above. No external
            # URLs or configured environment variables are read by these probes.
            script=(ROOT/'scripts/render_authorization_operator.sql').read_text()
            def probe(expected=None, db=database):
                with psycopg.connect(host='127.0.0.1',port=port,dbname=db,
                        user='sandbox_operator',password=passwords['sandbox_operator'],autocommit=True) as conn:
                    try:
                        conn.execute(script)
                    except psycopg.Error as error:
                        conn.execute('ROLLBACK')
                        if expected is None or expected not in str(error):
                            raise
                    else:
                        if expected is not None:
                            raise AssertionError('Operator accepted unsafe state: '+expected)
            probe('Wrong database', db='postgres')
            probe()  # Fresh CREATE ROLE and trusted pgcrypto, as non-superuser.
            probe()  # Safe repeat installation.
            with psycopg.connect(host='127.0.0.1',port=port,dbname=database,
                    user='sandbox_bootstrap',password=passwords['sandbox_bootstrap'],autocommit=True) as admin:
                tested_version=admin.info.server_version
                admin.execute('CREATE ROLE unsafe_group NOLOGIN')
                cases=[
                    ('ALTER ROLE hanuram_runtime CREATEROLE','ALTER ROLE hanuram_runtime NOCREATEROLE','elevated application login'),
                    ('ALTER ROLE hanuram_control REPLICATION','ALTER ROLE hanuram_control NOREPLICATION','elevated application login'),
                    ('GRANT unsafe_group TO hanuram_runtime WITH SET FALSE, INHERIT FALSE','REVOKE unsafe_group FROM hanuram_runtime','unexpected role memberships'),
                    ('GRANT hanuram_control TO hanuram_runtime','REVOKE hanuram_control FROM hanuram_runtime','unexpected role memberships'),
                    (f'GRANT CREATE ON DATABASE {database} TO hanuram_control',f'REVOKE CREATE ON DATABASE {database} FROM hanuram_control','CREATE privileges'),
                    ('CREATE TABLE public.unsafe_owned(id integer); ALTER TABLE public.unsafe_owned OWNER TO hanuram_runtime','DROP TABLE public.unsafe_owned','owns database objects'),
                    ('GRANT unsafe_group TO hanuram_identity_owner WITH SET FALSE, INHERIT FALSE','REVOKE unsafe_group FROM hanuram_identity_owner','Unsafe function-owner memberships'),
                    ('GRANT hanuram_jobs_owner TO unsafe_group','REVOKE hanuram_jobs_owner FROM unsafe_group','Unsafe function-owner memberships'),
                    ('ALTER ROLE hanuram_staff_owner INHERIT','ALTER ROLE hanuram_staff_owner NOINHERIT','Unsafe function-owner role'),
                    ('GRANT CREATE ON SCHEMA hanuram_crypto TO unsafe_group','REVOKE CREATE ON SCHEMA hanuram_crypto FROM unsafe_group','Unsafe hanuram_crypto'),
                    ('ALTER EXTENSION pgcrypto SET SCHEMA public','ALTER EXTENSION pgcrypto SET SCHEMA hanuram_crypto','another schema'),
                    ('REVOKE INHERIT OPTION FOR hanuram_identity_owner FROM sandbox_operator','GRANT hanuram_identity_owner TO sandbox_operator WITH INHERIT TRUE, SET TRUE',None),
                ]
                for setup,cleanup,expected in cases:
                    admin.execute(setup)
                    try:
                        probe(expected)
                    finally:
                        admin.execute(cleanup)
            print('Operator SQL: fresh/repeat installs, 12 boundary cases and wrong-database rejection passed on PostgreSQL '+str(tested_version),flush=True)
            with operator.begin() as connection:
                connection.execute(text('CREATE SCHEMA sandbox_guard'))
                connection.execute(text('CREATE TABLE sandbox_guard.identity(value text NOT NULL)'))
                connection.execute(text('INSERT INTO sandbox_guard.identity VALUES(:marker)'),{'marker':marker})
                connection.execute(text((ROOT/'scripts/render_authorization_operator.sql').read_text()))
            # All upgrade operations here are confined to the fresh cluster.
            run([sys.executable,'-m','alembic','upgrade','f91c320ab007'],cwd=ROOT,env=env)
            from test_key_provisioning_sandbox import run_tests
            with psycopg.connect(host='127.0.0.1',port=port,dbname=database,
                    user='sandbox_bootstrap',password=passwords['sandbox_bootstrap'],autocommit=True) as admin:
                run_tests(admin, urls['sandbox_operator'],
                    {kind:env['DATABASE_AUTH_'+kind.upper()+'_KEY'] for kind in ('identity','staff','jobs')})
            run([sys.executable,ROOT/'tests/security/context_contention_cases.py'],cwd=ROOT,env=env)
            run([sys.executable,'-m','alembic','upgrade','head'],cwd=ROOT,env=env)
            # Verify the new migration's reversible trigger change in this cluster.
            with operator.connect() as connection:
                before = connection.execute(text("SELECT oid,proowner,proacl::text,proconfig::text FROM pg_proc WHERE oid='hanuram_auth.guard_row()'::regprocedure")).one()
            run([sys.executable,'-m','alembic','downgrade','f91c320ab011'],cwd=ROOT,env=env)
            run([sys.executable,'-m','alembic','upgrade','head'],cwd=ROOT,env=env)
            with operator.connect() as connection:
                after = connection.execute(text("SELECT oid,proowner,proacl::text,proconfig::text FROM pg_proc WHERE oid='hanuram_auth.guard_row()'::regprocedure")).one()
                assert before == after, 'Trigger function identity, owner, ACL or search path changed'
            # Bound regressions that would otherwise hang HTTP dependency setup.
            test_env={**env, 'PGOPTIONS':'-c lock_timeout=5000 -c statement_timeout=15000'}
            run([sys.executable,ROOT/'tests/security/test_authorization_roles.py'],cwd=ROOT,env=test_env)
            if args.legacy_tests:
                legacy='authorization_legacy_test'
                with psycopg.connect(host='127.0.0.1',port=port,dbname='postgres',user='sandbox_bootstrap',password=passwords['sandbox_bootstrap'],autocommit=True) as bootstrap:
                    bootstrap.execute(sql.SQL('CREATE DATABASE {} OWNER sandbox_operator').format(sql.Identifier(legacy)))
                legacy_url=URL.create('postgresql+psycopg',username='sandbox_bootstrap',password=passwords['sandbox_bootstrap'],host='127.0.0.1',port=port,database=legacy).render_as_string(hide_password=False)
                legacy_env={**env,'TEST_DATABASE_URL':legacy_url,'REQUIRE_RLS':'false'}
                run([sys.executable,ROOT/'scripts/run_enterprise_tests.py','--no-migrations'],cwd=ROOT,env=legacy_env)
            operator.dispose()
        finally:
            if started:
                run([binpath/('pg_ctl'+suffix),'-D',data,'-m','immediate','-w','stop'],stdout=subprocess.DEVNULL)
                print('Disposable PostgreSQL stopped; temporary cluster removed.',flush=True)


if __name__=='__main__':
    main()
