"""Extend existing onboarding records without replacing tenant security policies."""
import importlib.util
from pathlib import Path
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'f91c320ab009'
down_revision = 'f91c320ab008'
branch_labels = None
depends_on = None


def previous_policy():
    path = Path(__file__).with_name('f91c320ab006_verified_authorization.py')
    spec = importlib.util.spec_from_file_location('original_authorization', path)
    if spec is None or spec.loader is None:
        raise ImportError(f'Unable to load authorization policy from {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ALLOWED_SQL


def upgrade():
    for name in ['assigned_admin_id', 'verified_by']:
        op.add_column('onboarding_requests', sa.Column(name, sa.Integer(), sa.ForeignKey('users.id')))
    for name in ['accepted_at', 'setup_started_at', 'action_requested_at', 'tenant_confirmed_at', 'verified_at', 'connected_at']:
        op.add_column('onboarding_requests', sa.Column(name, sa.DateTime(timezone=True)))
    op.add_column('onboarding_requests', sa.Column('required_action', sa.String(40)))
    op.add_column('onboarding_requests', sa.Column('rejection_reason', sa.Text()))
    op.add_column('onboarding_requests', sa.Column('history', JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column('onboarding_requests', sa.Column('verification', JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    # Preserve old status in history. Legacy ready was not fully Meta-verified;
    # re-review rather than manufacturing a successful verification.
    operator = op.get_bind().scalar(sa.text('SELECT current_user'))
    quoted_operator = op.get_bind().dialect.identifier_preparer.quote(operator)
    op.execute(f'CREATE POLICY onboarding_migration ON onboarding_requests TO {quoted_operator} USING (true) WITH CHECK (true)')
    op.execute("""UPDATE onboarding_requests SET history=jsonb_build_array(jsonb_build_object(
        'event','legacy_import','previous_status',status,'at',statement_timestamp())),
        status=CASE WHEN status IN ('needs_customer_action','provider_review','billing_pending','ready')
                    THEN 'requested' ELSE status END""")
    op.execute('DROP POLICY onboarding_migration ON onboarding_requests')
    # Fail safely on legacy duplicates; operators must review rather than delete history.
    op.create_index('uq_onboarding_active_org', 'onboarding_requests', ['organization_id'], unique=True,
        postgresql_where=sa.text("status IN ('requested','accepted','setup_in_progress','action_required','connected')"))
    original = previous_policy()
    old = """(tab='onboarding_requests' AND (command='select' OR (command='update' AND r->>'id'=c->>'resource')))
            OR (tab='whatsapp_connections' AND command='select' AND coalesce(target,false))"""
    new = """(tab='onboarding_requests' AND (command='select' OR
                (command='update' AND coalesce(target,false) AND r->>'id'=c->>'resource')))
            OR (coalesce(target,false) AND command='select' AND tab IN
                ('whatsapp_connections','organizations','tenants','subscriptions','contact_consents','message_records'))
            OR (coalesce(target,false) AND tab='message_records' AND command='insert'
                AND r->>'recipient'=c->>'test_phone' AND r->>'sender_phone_id'=c->>'test_sender')"""
    if old not in original:
        raise RuntimeError('Original onboarding policy changed; review this migration')
    policy = original.replace(old, new)
    policy = policy.replace("tab IN ('organizations','whatsapp_connections','whatsapp_templates','contact_consents')",
        "tab IN ('organizations','whatsapp_connections','whatsapp_templates','contact_consents','onboarding_requests','subscriptions')")
    op.execute(policy.replace('CREATE FUNCTION hanuram_auth.allowed', 'CREATE OR REPLACE FUNCTION hanuram_auth.allowed'))
    op.execute('GRANT SELECT ON whatsapp_connections,contact_consents,message_records TO hanuram_control')
    op.execute('GRANT INSERT ON message_records TO hanuram_control')
    # UPDATE USING permits row locks; WITH CHECK false prohibits actual changes.
    c = 'hanuram_auth.context()'
    for table, org in [('organizations', 'id')]:
        op.execute(f"CREATE POLICY onboarding_lock ON {table} FOR UPDATE TO hanuram_control USING "
            f"({c}->>'purpose'='staff.onboarding.manage' AND hanuram_auth.permission('onboarding.manage') "
            f"AND tenant_id=({c}->>'target_tenant')::integer AND {org}=({c}->>'target_org')::integer) WITH CHECK (false)")


def downgrade():
    # Refuse destructive automatic rollback of production history.
    raise RuntimeError('Managed onboarding rollback requires a reviewed data-preserving migration')
