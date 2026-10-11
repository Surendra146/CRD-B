"""Guard account ownership and require atomic staff auditing under FORCE RLS."""
from pathlib import Path

from alembic import op
import sqlalchemy as sa

revision = 'f91c320ab007'
down_revision = 'f91c320ab006'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.text((Path(__file__).parents[1] / 'authorization' / 'f91c320ab007.sql').read_text()))
    c='hanuram_auth.context()'
    # Only the SQL provisioning function can use these owner policies.
    op.execute('GRANT SELECT,UPDATE ON users TO hanuram_staff_owner')
    op.execute('GRANT SELECT,INSERT,UPDATE ON platform_staff TO hanuram_staff_owner')
    op.execute('GRANT SELECT,INSERT ON audit_events TO hanuram_staff_owner')
    op.execute(f"CREATE POLICY operator_user ON users TO hanuram_staff_owner USING ({c}->>'purpose'='operator.staff' AND email={c}->>'email') WITH CHECK (false)")
    op.execute(f"CREATE POLICY operator_membership ON platform_staff TO hanuram_staff_owner USING ({c}->>'purpose'='operator.staff' AND user_id=({c}->>'sub')::integer) WITH CHECK ({c}->>'purpose'='operator.staff' AND user_id=({c}->>'sub')::integer)")
    op.execute(f"CREATE POLICY staff_audit_read ON audit_events FOR SELECT TO hanuram_staff_owner USING ({c}->>'purpose' LIKE 'staff.%' AND hanuram_auth.permission(substring({c}->>'purpose' FROM 7)) AND resource_id={c}->>'resource' AND actor_id=({c}->>'sub')::integer AND action={c}->>'action')")
    op.execute(f"CREATE POLICY operator_audit ON audit_events FOR INSERT TO hanuram_staff_owner WITH CHECK ({c}->>'purpose'='operator.staff' AND actor_id=({c}->>'sub')::integer AND tenant_id=({c}->>'tenant')::integer AND organization_id=({c}->>'org')::integer AND action='platform.staff.permissions.updated')")
    operator=op.get_bind().scalar(sa.text('SELECT current_user'))
    identifier=op.get_bind().dialect.identifier_preparer.quote(operator)
    op.execute(f'GRANT EXECUTE ON FUNCTION hanuram_auth.operator_staff(text,jsonb,boolean) TO {identifier}')
    for table in ['users','organizations','whatsapp_bulk_jobs','message_records','contact_consents']:
        op.execute(f'CREATE TRIGGER authorization_guard BEFORE INSERT OR UPDATE ON public.{table} FOR EACH ROW EXECUTE FUNCTION hanuram_auth.guard_row()')
    op.execute("CREATE TRIGGER staff_audit_receipt BEFORE INSERT ON public.audit_events FOR EACH ROW WHEN (session_user='hanuram_control') EXECUTE FUNCTION hanuram_auth.audit_receipt()")
    for table, commands in [('subscriptions','INSERT OR UPDATE'),('subscription_plans','INSERT'),('tenants','UPDATE'),('onboarding_requests','UPDATE'),('usage_entries','INSERT')]:
        op.execute(f"CREATE TRIGGER staff_change BEFORE {commands} ON public.{table} FOR EACH ROW WHEN (session_user='hanuram_control') EXECUTE FUNCTION hanuram_auth.record_staff_change()")
        op.execute(f"CREATE CONSTRAINT TRIGGER staff_audit AFTER {commands} ON public.{table} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN (session_user='hanuram_control') EXECUTE FUNCTION hanuram_auth.require_staff_audit()")
    op.execute("CREATE UNIQUE INDEX uq_subscription_request_resource ON public.audit_events(resource_id,(details->>'request_id')) WHERE action LIKE 'platform.subscription.%' AND details->>'request_id' IS NOT NULL")


def downgrade():
    raise RuntimeError('Authorization rollback requires a reviewed security rollback and backup')
