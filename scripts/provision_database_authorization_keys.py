"""Explicit offline key provisioning; NEVER called by application startup."""
import argparse
import getpass
import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def provision_keys(connection, secrets):
    """Insert initial keys within the caller's transaction; never rotate keys."""
    if set(secrets) != {'identity','staff','jobs'} or any(
        len(value)<32 for value in secrets.values()
    ) or len(set(secrets.values())) != 3:
        raise RuntimeError('Use three distinct keys of at least 32 characters')
    database, session, current = connection.execute(text(
        'SELECT current_database(), session_user, current_user'
    )).one()
    if database != 'hanuram_production':
        raise RuntimeError('Expected database hanuram_production')
    if session != 'hanuram_production_user' or current != session:
        raise RuntimeError('Connect directly as hanuram_production_user before SET ROLE')
    owner = connection.scalar(text(
        "SELECT oid FROM pg_roles WHERE rolname='hanuram_identity_owner'"
    ))
    if owner is None or not connection.scalar(text(
        "SELECT pg_has_role(current_user, :owner, 'SET')"
    ), {'owner':owner}):
        raise RuntimeError('Operator cannot SET ROLE to hanuram_identity_owner')
    connection.execute(text('SET LOCAL ROLE hanuram_identity_owner'))
    for table in ('installation','signing_keys'):
        if not connection.scalar(text(
            "SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='hanuram_auth' AND c.relname=:table "
            "AND c.relkind='r' AND c.relowner=:owner)"
        ), {'table':table,'owner':owner}):
            raise RuntimeError('Expected authorization table missing or incorrectly owned')
    connection.execute(text('LOCK TABLE hanuram_auth.installation IN SHARE MODE'))
    if not connection.scalar(text(
        "SELECT count(*)=1 AND bool_and(id IS NOT NULL AND pg_typeof(id)='uuid'::regtype) "
        'FROM hanuram_auth.installation'
    )):
        raise RuntimeError('Expected exactly one installation UUID')
    # Serialize initial provisioning, including concurrent invocations. No keys
    # are selected into Python or written to logs.
    connection.execute(text('LOCK TABLE hanuram_auth.signing_keys IN EXCLUSIVE MODE'))
    if connection.scalar(text('SELECT EXISTS(SELECT 1 FROM hanuram_auth.signing_keys)')):
        raise RuntimeError('Signing keys already exist; use a separately reviewed rotation procedure')
    for purpose, secret in secrets.items():
        connection.execute(text(
            'INSERT INTO hanuram_auth.signing_keys(purpose,secret) VALUES(:purpose,:secret)'
        ), {'purpose':purpose,'secret':secret})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true',help='Explicitly store the three keys in the selected database')
    args=parser.parse_args()
    if not args.apply:
        parser.error('Review the deployment guide, then explicitly supply --apply')
    raw=os.environ.get('OPERATOR_DATABASE_URL')
    if not raw:
        parser.error('Set a separate OPERATOR_DATABASE_URL in the process environment')
    secrets={kind:getpass.getpass('Matching DATABASE_AUTH_'+kind.upper()+'_KEY (hidden): ')
             for kind in ('identity','staff','jobs')}
    if any(len(value)<32 for value in secrets.values()) or len(set(secrets.values()))!=3:
        parser.error('Use three distinct random keys, each at least 32 characters')
    engine=None
    try:
        engine=create_engine(make_url(raw.replace('postgres://','postgresql://',1)).set(drivername='postgresql+psycopg'),hide_parameters=True,echo=False)
        with engine.begin() as connection:
            provision_keys(connection, secrets)
        print('Stored the three keys. No key values were printed.')
    except Exception:
        raise SystemExit('Initial key provisioning failed; transaction rolled back. Check database, operator, installation, SET ROLE access, and existing keys. Rotation requires a separate procedure.') from None
    finally:
        if engine is not None:
            engine.dispose()


if __name__=='__main__':
    main()
