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
