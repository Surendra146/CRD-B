"""Move authorization-context retention out of application transactions."""
from pathlib import Path

from alembic import op
import sqlalchemy as sa

revision = "f91c320ab008"
down_revision = "f91c320ab007"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.text((Path(__file__).parents[1] / "authorization" / "f91c320ab008.sql").read_text()))
    # Use the installation operator already captured by revision 007, rather
    # than granting maintenance to whichever login executes this migration.
    operators = op.get_bind().execute(sa.text("""
        SELECT grantee.rolname
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid=p.pronamespace
        CROSS JOIN LATERAL aclexplode(p.proacl) a
        JOIN pg_roles grantee ON grantee.oid=a.grantee
        WHERE n.nspname='hanuram_auth'
          AND p.oid='hanuram_auth.operator_staff(text,jsonb,boolean)'::regprocedure
          AND a.privilege_type='EXECUTE' AND a.grantee<>p.proowner
    """)).scalars().all()
    if len(operators) != 1 or operators[0] in ('hanuram_runtime', 'hanuram_control'):
        raise RuntimeError("Exactly one installation operator grant is required for context maintenance")
    operator = operators[0]
    identifier = op.get_bind().dialect.identifier_preparer.quote(operator)
    op.execute(f"GRANT EXECUTE ON FUNCTION hanuram_auth.prune_contexts(integer) TO {identifier}")


def downgrade():
    raise RuntimeError("Context-retention rollback would reintroduce authorization lock contention")
