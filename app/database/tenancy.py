"""Transaction-local PostgreSQL scope, renewed after every Session commit."""
from sqlalchemy import event, text
from sqlalchemy.orm import Session


def apply_scope(connection, scope):
    if connection.dialect.name == "postgresql":
        connection.execute(text("SELECT set_config('app.tenant_id', :tenant, true), set_config('app.organization_id', :organization, true)"),
                           {"tenant": str(scope[0]) if scope else "", "organization": str(scope[1]) if scope else ""})


def bind_scope(session, tenant_id, organization_id):
    scope = (int(tenant_id), int(organization_id))
    if session.info.get("tenant_scope") not in (None, scope):
        raise RuntimeError("A database session cannot change tenant identity")
    session.info["tenant_scope"] = scope
    if session.in_transaction():
        apply_scope(session.connection(), scope)


@event.listens_for(Session, "after_begin")
def transaction_scope(session, transaction, connection):
    # Empty transaction-local context denies unscoped SQL and clears pooled state.
    apply_scope(connection, session.info.get("tenant_scope"))
    from app.database.authorization import apply_authority
    apply_authority(connection, session.info.get("database_authority"))


def verify_runtime_role(connection):
    role = connection.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")).one()
    if role.rolsuper or role.rolbypassrls:
        raise RuntimeError("Runtime database role must not be superuser or BYPASSRLS")
    from app.database.connection import Base
    from app import models  # noqa: F401; register every business table.
    protected_tables = [table.name for table in Base.metadata.tables.values() if "tenant_id" in table.c or table.name == "tenants"]
    for name in protected_tables:
        protected = connection.scalar(text("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid = to_regclass(:name)"), {"name": name})
        if not protected:
            raise RuntimeError(f"Forced tenant RLS is required on {name} before enterprise startup")


def verify_authorization_installation(connection, expected_login):
    import hashlib
    import hmac
    from app.config.settings import get_settings
    if any(len(key) < 32 for key in get_settings().database_authorization_keys.values()):
        raise RuntimeError('Provision all three database authorization keys before startup')
    row = connection.execute(text('SELECT current_user,rolsuper,rolbypassrls,rolcreaterole,rolcreatedb FROM pg_roles WHERE rolname=current_user')).one()
    if row[0] != expected_login or any(row[1:]):
        raise RuntimeError('Use the expected restricted runtime/control login without administrative attributes')
    if connection.scalar(text("SELECT count(*) FROM pg_roles WHERE rolname<>current_user AND pg_has_role(current_user,oid,'MEMBER')")):
        raise RuntimeError('Application logins must not have inherited or assumable group roles')
    for owner in ('hanuram_identity_owner','hanuram_staff_owner','hanuram_jobs_owner'):
        row = connection.execute(text('SELECT rolcanlogin,rolsuper,rolbypassrls,rolcreaterole,rolcreatedb FROM pg_roles WHERE rolname=:owner'), {'owner': owner}).first()
        if not row or any(row) or connection.scalar(text("SELECT pg_has_role(current_user,:owner,'MEMBER')"), {'owner': owner}):
            raise RuntimeError('Application logins must not inherit or assume function owner roles')
    if connection.scalar(text("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('public','hanuram_auth','hanuram_crypto') AND c.relowner=(SELECT oid FROM pg_roles WHERE rolname=current_user)")):
        raise RuntimeError('Application logins must not own authorization or application objects')
    if connection.scalar(text("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='hanuram_auth' AND p.prosecdef AND (NOT coalesce(p.proconfig,'{}'::text[]) @> ARRAY['search_path=pg_catalog, hanuram_auth, pg_temp'] OR EXISTS(SELECT 1 FROM aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) WHERE grantee=0 AND privilege_type='EXECUTE'))")):
        raise RuntimeError('Unsafe authorization function search_path or PUBLIC EXECUTE privilege')
    if connection.scalar(text("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_roles r ON r.oid=p.proowner WHERE n.nspname='hanuram_auth' AND p.prosecdef AND r.rolname NOT IN ('hanuram_identity_owner','hanuram_staff_owner','hanuram_jobs_owner')")):
        raise RuntimeError('Authorization function ownership is inconsistent')
    for schema in ('public','hanuram_auth','hanuram_crypto'):
        if connection.scalar(text("SELECT has_schema_privilege(current_user,:schema,'CREATE')"),{'schema':schema}):
            raise RuntimeError('Application logins must not create objects in trusted schemas')
    if connection.scalar(text("SELECT version_num FROM public.alembic_version")) != 'f91c320ab007':
        raise RuntimeError('Install the reviewed authorization migrations before startup')
    for table in ('platform_staff','subscription_plans'):
        if not connection.scalar(text('SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid=to_regclass(:table)'), {'table': table}):
            raise RuntimeError('Staff and plan RLS protections are required')
    identity=connection.execute(text('SELECT hanuram_auth.installation_id()::text,session_user,pg_backend_pid()::text,txid_current()::text')).one()
    challenge=':'.join(identity)
    for kind,secret in get_settings().database_authorization_keys.items():
        signature=hmac.new(secret.encode(),challenge.encode(),hashlib.sha256).hexdigest()
        if not connection.scalar(text('SELECT hanuram_auth.check_key(:kind,:signature)'),{'kind':kind,'signature':signature}):
            raise RuntimeError('Application authorization keys do not match the selected database installation')
    return identity[0]
