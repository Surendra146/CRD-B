"""Read-only installation checks. Does not import the app or load its .env.

Supply an operator URL in AUTHORIZATION_PREFLIGHT_URL in the process environment.
Output contains catalog metadata only; credentials and exception messages are never
printed. This script does not install extensions, grant roles, or run migrations.
"""
import argparse
import json
import os
import sys
from collections.abc import Mapping

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool


OWNER_ROLES = ("hanuram_identity_owner", "hanuram_staff_owner", "hanuram_jobs_owner")


def assess(snapshot: Mapping) -> dict:
    """Fail closed on absent evidence; availability is not an installed extension."""
    blockers = []
    requirements = []
    operator = snapshot["operator"]
    roles = snapshot["roles"]
    runtime, control = snapshot["runtime_role"], snapshot["control_role"]
    if int(snapshot["server_version_num"]) < 160000:
        blockers.append("This preflight requires PostgreSQL 16+ role membership semantics.")
    if runtime == control:
        blockers.append("Runtime and control role names must be distinct.")
    if operator["name"] in {runtime, control}:
        blockers.append("Use a separate migration/operator login, not an application login.")
    if operator["superuser"] or operator["bypass_rls"]:
        blockers.append("Use a NOSUPERUSER NOBYPASSRLS operator to verify Render-compatible privileges.")
    if not snapshot["database_create"]:
        blockers.append("Operator requires CREATE on the database for private authorization schemas.")
    if not snapshot["public_schema_create"]:
        blockers.append("Operator requires CREATE on public to install the existing migration chain.")
    if snapshot["unowned_tables"]:
        blockers.append("Operator does not own all existing public tables; ownership or owner membership must be reviewed.")
    extension = snapshot.get("pgcrypto")
    if not extension:
        blockers.append("pgcrypto is unavailable; a provider must make the extension available.")
    elif not extension["installed"]:
        if not extension["trusted"]:
            blockers.append("Available pgcrypto is not marked trusted; do not attempt privileged installation.")
        requirements.append("Install pgcrypto manually in a trusted schema using the reviewed operator procedure.")
    for name in (runtime, control):
        role = roles.get(name)
        if not role:
            if not operator["create_role"]:
                blockers.append(f"Cannot provision missing application login {name}: operator lacks CREATEROLE.")
            requirements.append(f"Provision distinct application login {name} before final grant validation.")
            continue
        if not role["login"]:
            blockers.append(f"{name} is not a LOGIN role.")
        if any(role[key] for key in ("superuser", "bypass_rls", "create_role", "create_db")):
            blockers.append(f"{name} has elevated role attributes; application logins must not have them.")
        if snapshot["application_owned_tables"].get(name):
            blockers.append(f"{name} owns public tables and can change their RLS; move ownership to an operator role.")
    for name in OWNER_ROLES:
        role = roles.get(name)
        if not role:
            if not operator["create_role"]:
                blockers.append(f"Cannot provision {name}: operator lacks CREATEROLE.")
            else:
                requirements.append(f"Create {name} as NOLOGIN NOSUPERUSER NOBYPASSRLS; temporarily authorize operator SET ROLE.")
            continue
        if any(role[key] for key in ("login", "superuser", "bypass_rls", "create_role", "create_db")):
            blockers.append(f"Function owner {name} must be NOLOGIN without elevated attributes.")
        if not snapshot["operator_set_owner"].get(name):
            blockers.append(f"Operator cannot SET ROLE to {name}, required to transfer function ownership.")
        for login in (runtime, control):
            if snapshot["application_owner_memberships"].get(login, {}).get(name):
                blockers.append(f"{login} must not be a member of function owner {name}.")
    return {"installation_prerequisites_satisfied": not blockers,
            "blockers": blockers, "manual_requirements": requirements,
            "scope": "Installation prerequisites only; final policies, function ACLs and restricted-role tests are still required.",
            "catalog": dict(snapshot)}


def collect(connection, runtime_role: str, control_role: str) -> dict:
    # The first statement runs inside SQLAlchemy's transaction. Even a future
    # accidental DDL/DML addition will be rejected by PostgreSQL.
    connection.execute(text("SET TRANSACTION READ ONLY"))
    connection.execute(text("SET LOCAL statement_timeout = '10s'"))
    connection.execute(text("SET LOCAL lock_timeout = '2s'"))
    version = int(connection.scalar(text("SELECT current_setting('server_version_num')")))
    if version < 160000:
        raise ValueError("unsupported_server")
    operator_name = connection.scalar(text("SELECT current_user"))
    role_rows = connection.execute(text("""
        SELECT rolname AS name, rolcanlogin AS login, rolsuper AS superuser,
               rolbypassrls AS bypass_rls, rolcreaterole AS create_role,
               rolcreatedb AS create_db
        FROM pg_catalog.pg_roles
        WHERE rolname = ANY(:names)
        ORDER BY rolname
    """), {"names": [operator_name, runtime_role, control_role, *OWNER_ROLES]}).mappings().all()
    roles = {row["name"]: dict(row) for row in role_rows}
    privileges = connection.execute(text("""
        SELECT has_database_privilege(current_user, current_database(), 'CREATE') AS database_create,
               has_schema_privilege(current_user, 'public', 'CREATE') AS public_schema_create
    """)).mappings().one()
    extension = connection.execute(text("""
        SELECT v.trusted, e.extname IS NOT NULL AS installed,
               n.nspname AS installed_schema
        FROM pg_catalog.pg_available_extension_versions v
        JOIN pg_catalog.pg_available_extensions a
          ON a.name = v.name AND a.default_version = v.version
        LEFT JOIN pg_catalog.pg_extension e ON e.extname = v.name
        LEFT JOIN pg_catalog.pg_namespace n ON n.oid = e.extnamespace
        WHERE v.name = 'pgcrypto'
    """)).mappings().first()
    tables = connection.execute(text("""
        SELECT c.relname AS name, r.rolname AS owner,
               pg_has_role(current_user, c.relowner, 'USAGE') AS operator_owns,
               c.relrowsecurity AS rls, c.relforcerowsecurity AS force_rls
        FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_catalog.pg_roles r ON r.oid = c.relowner
        WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
        ORDER BY c.relname
    """)).mappings().all()
    owner_set = {}
    memberships = {runtime_role: {}, control_role: {}}
    for owner in OWNER_ROLES:
        if owner not in roles:
            continue
        owner_set[owner] = connection.scalar(text("SELECT pg_has_role(current_user, :owner, 'SET')"), {"owner": owner})
        for login in (runtime_role, control_role):
            if login in roles:
                memberships[login][owner] = connection.scalar(text("SELECT pg_has_role(:login, :owner, 'MEMBER')"), {"login": login, "owner": owner})
    return {"server_version_num": version, "operator": roles[operator_name],
            "runtime_role": runtime_role, "control_role": control_role, "roles": roles,
            **dict(privileges), "pgcrypto": dict(extension) if extension else None,
            "public_tables": [dict(row) for row in tables],
            "unowned_tables": [row["name"] for row in tables if not row["operator_owns"]],
            "application_owned_tables": {login: [row["name"] for row in tables if row["owner"] == login]
                                         for login in (runtime_role, control_role)},
            "operator_set_owner": owner_set, "application_owner_memberships": memberships}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-role", default="hanuram_runtime")
    parser.add_argument("--control-role", default="hanuram_control")
    args = parser.parse_args(argv)
    raw_url = os.environ.get("AUTHORIZATION_PREFLIGHT_URL")
    if not raw_url:
        print(json.dumps({"error": "Set AUTHORIZATION_PREFLIGHT_URL to a separate operator connection in the process environment. No .env is loaded."}))
        return 2
    engine = None
    try:
        url = make_url(raw_url.replace("postgres://", "postgresql://", 1))
        if url.get_backend_name() != "postgresql":
            raise ValueError("postgresql_required")
        engine = create_engine(url.set(drivername="postgresql+psycopg"), poolclass=NullPool,
                               echo=False, hide_parameters=True, connect_args={"connect_timeout": 10})
        with engine.connect() as connection:
            report = assess(collect(connection, args.runtime_role, args.control_role))
            connection.rollback()
        print(json.dumps(report, indent=2))
        return 0 if report["installation_prerequisites_satisfied"] else 1
    except Exception as error:
        # Do not emit raw exception text, DSNs, password fields or driver details.
        state = getattr(getattr(error, "orig", error), "sqlstate", None)
        print(json.dumps({"error": "Read-only privilege verification failed; no privileges were changed.",
                          "exception_type": type(error).__name__, "sqlstate": state}))
        return 2
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
