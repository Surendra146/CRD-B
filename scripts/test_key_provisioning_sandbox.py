"""Called only by the runner owning a newly initialized disposable cluster."""
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from psycopg import sql

from provision_database_authorization_keys import provision_keys


def run_tests(admin, operator_url, keys):
    password=make_url(operator_url).password
    admin.execute(sql.SQL('CREATE ROLE hanuram_production_user LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD {}').format(sql.Literal(password)))
    admin.execute('GRANT hanuram_identity_owner TO hanuram_production_user WITH SET TRUE, INHERIT FALSE')
    url=make_url(operator_url).set(username='hanuram_production_user')
    engines=[create_engine(value, hide_parameters=True, echo=False) for value in
             (url, url.set(database='postgres'), make_url(operator_url))]
    target, wrong_database, wrong_operator=engines
    def attempt(engine=target, expected=None):
        try:
            with engine.begin() as connection:
                provision_keys(connection, keys)
        except RuntimeError as error:
            if expected is None or expected not in str(error):
                raise AssertionError('Unexpected provisioning result') from None
        except Exception:
            if expected != 'database failure':
                raise AssertionError('Unexpected database failure') from None
        else:
            if expected is not None:
                raise AssertionError('Unsafe provisioning accepted')
    try:
        attempt(wrong_database, 'Expected database')
        attempt(wrong_operator, 'Connect directly')
        with target.begin() as connection:
            connection.execute(text('SET LOCAL ROLE hanuram_identity_owner'))
            try:
                provision_keys(connection, keys)
            except RuntimeError as error:
                assert 'Connect directly' in str(error)
            else:
                raise AssertionError('Already assumed role was accepted')
        admin.execute('REVOKE hanuram_identity_owner FROM hanuram_production_user')
        attempt(expected='cannot SET ROLE')
        admin.execute('GRANT hanuram_identity_owner TO hanuram_production_user WITH SET TRUE, INHERIT FALSE')
        for table in ('installation','signing_keys'):
            admin.execute(sql.SQL('ALTER TABLE hanuram_auth.{} RENAME TO absent_table').format(sql.Identifier(table)))
            try:
                attempt(expected='table missing')
            finally:
                admin.execute(sql.SQL('ALTER TABLE hanuram_auth.absent_table RENAME TO {}').format(sql.Identifier(table)))
        # Cause the third INSERT to fail, proving earlier INSERTs roll back.
        admin.execute("CREATE FUNCTION hanuram_auth.fail_test_jobs() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.purpose='jobs' THEN RAISE EXCEPTION 'Injected test failure'; END IF; RETURN NEW; END $$")
        admin.execute('CREATE TRIGGER fail_test_jobs BEFORE INSERT ON hanuram_auth.signing_keys FOR EACH ROW EXECUTE FUNCTION hanuram_auth.fail_test_jobs()')
        attempt(expected='database failure')
        assert admin.execute('SELECT count(*) FROM hanuram_auth.signing_keys').fetchone()[0]==0
        admin.execute('DROP TRIGGER fail_test_jobs ON hanuram_auth.signing_keys')
        admin.execute('DROP FUNCTION hanuram_auth.fail_test_jobs()')
        attempt()
        # Both partial and full preexisting provisioning are refused.
        attempt(expected='already exist')
        admin.execute("DELETE FROM hanuram_auth.signing_keys WHERE purpose='jobs'")
        attempt(expected='already exist')
        assert admin.execute('SELECT count(*) FROM hanuram_auth.signing_keys').fetchone()[0]==2
        admin.execute('INSERT INTO hanuram_auth.signing_keys(purpose,secret) VALUES(%s,%s)', ('jobs',keys['jobs']))
        assert admin.execute('SELECT count(*) FROM hanuram_auth.signing_keys').fetchone()[0]==3
        # Compare in the database with bound parameters; never fetch key values.
        for purpose, secret in keys.items():
            assert admin.execute('SELECT secret=%s FROM hanuram_auth.signing_keys WHERE purpose=%s', (secret,purpose)).fetchone()[0]
        print('Key provisioning: success, wrong database/operator, missing SET authority/tables, duplicate refusal, and third-insert rollback passed.', flush=True)
    finally:
        for engine in engines:
            engine.dispose()
        admin.execute('REVOKE hanuram_identity_owner FROM hanuram_production_user')
        admin.execute('DROP ROLE hanuram_production_user')
