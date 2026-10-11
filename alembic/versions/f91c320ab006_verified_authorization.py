"""Verified transaction authority under FORCE RLS, without bypass privileges.

Requires operator preparation in scripts/render_authorization_operator.sql.
No signing secrets or passwords are embedded in this migration.
"""
from pathlib import Path

from alembic import op
import sqlalchemy as sa

revision = "f91c320ab006"
down_revision = "f91c320ab005"
branch_labels = None
depends_on = None

TABLES = ['generic_json_records', 'organizations', 'business_profiles', 'contact_consents',
          'customers', 'saas_invoices', 'subscriptions', 'usage_entries', 'users', 'whatsapp_templates',
          'audit_events', 'campaigns', 'consent_events', 'data_uploads', 'gmaps_extracted_leads',
          'onboarding_requests', 'segments', 'whatsapp_auto_responders', 'whatsapp_bulk_jobs',
          'whatsapp_connections', 'whatsapp_group_tasks', 'whatsapp_signup_attempts', 'campaign_outbox',
          'data_upload_rows', 'message_records', 'tenants']
OWNERS = ['hanuram_identity_owner', 'hanuram_staff_owner', 'hanuram_jobs_owner']

ALLOWED_SQL = r"""
CREATE FUNCTION hanuram_auth.allowed(tab text, command text, r jsonb) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = pg_catalog, hanuram_auth, pg_temp AS $$
DECLARE c jsonb := hanuram_auth.context(); p text:=c->>'purpose'; a jsonb;
    t integer; o integer; scoped boolean; target boolean; permission text;
BEGIN
    IF c='{}'::jsonb THEN RETURN false; END IF;
    t:=CASE WHEN tab='tenants' THEN (r->>'id')::integer ELSE (r->>'tenant_id')::integer END;
    o:=CASE WHEN tab='organizations' THEN (r->>'id')::integer ELSE (r->>'organization_id')::integer END;
    IF tab='platform_staff' THEN
        RETURN command='select' AND (r->>'user_id')::integer=(c->>'sub')::integer
            AND p IN ('account','identity.user','tenant') AND hanuram_auth.active_subject();
    END IF;
    IF tab='subscription_plans' THEN
        IF command='select' THEN RETURN session_user='hanuram_runtime' OR
            (p IN ('account','identity.user') AND hanuram_auth.active_subject()) OR
            (p LIKE 'staff.%' AND hanuram_auth.permission(substring(p FROM 7))); END IF;
        RETURN session_user='hanuram_control' AND command='insert' AND p='staff.plans.manage'
            AND r->>'id'=c->>'resource' AND hanuram_auth.permission('plans.manage');
    END IF;
    IF session_user='hanuram_control' AND p='identity.email' THEN
        RETURN tab='users' AND command='select' AND r->>'email'=c->>'email';
    END IF;
    IF session_user='hanuram_control' AND p='identity.user' THEN
        a:=hanuram_auth.subject();
        RETURN command='select' AND hanuram_auth.active_subject() AND
          ((tab='users' AND r->>'id'=c->>'sub') OR
           (tab='organizations' AND (r->>'id')::integer=(a->>'org')::integer) OR
           (tab='tenants' AND (r->>'id')::integer=(a->>'tenant')::integer));
    END IF;
    IF p IN ('tenant','account','job.scope','upload.scope') THEN
        a:=hanuram_auth.subject();
        scoped:=t=(c->>'tenant')::integer AND (tab='tenants' OR o=(c->>'org')::integer)
            AND hanuram_auth.active_subject() AND (a->>'org')::integer=(c->>'org')::integer;
        IF NOT coalesce(scoped,false) THEN RETURN false; END IF;
        IF a->>'role'='viewer' AND command<>'select' THEN RETURN false; END IF;
        IF tab IN ('tenants','saas_invoices','subscriptions','usage_entries','platform_staff') THEN RETURN command='select'; END IF;
        IF tab='users' THEN
            IF command='select' THEN RETURN r->>'id'=c->>'sub' OR (a->>'role') IN ('owner','admin'); END IF;
            RETURN session_user='hanuram_control' AND p='account' AND
                (r->>'id'=c->>'sub' OR (a->>'role') IN ('owner','admin'));
        END IF;
        IF session_user='hanuram_control' THEN
            RETURN p='account' AND tab='organizations' AND
                (command='select' OR (command='update' AND a->>'role' IN ('owner','admin')));
        END IF;
        IF p='job.scope' THEN
            IF tab='whatsapp_bulk_jobs' THEN RETURN r->>'id'=c->>'job' AND command IN ('select','update'); END IF;
            IF tab='campaign_outbox' THEN RETURN r->>'bulk_job_id'=c->>'job' AND command IN ('select','update'); END IF;
            IF tab='message_records' THEN RETURN r->>'bulk_job_id'=c->>'job' AND command IN ('select','insert'); END IF;
            RETURN command='select' AND tab IN ('organizations','whatsapp_connections','whatsapp_templates','contact_consents');
        END IF;
        IF p='upload.scope' THEN
            IF tab='data_uploads' THEN RETURN r->>'id'=c->>'upload' AND command IN ('select','update'); END IF;
            IF tab='data_upload_rows' THEN RETURN r->>'upload_id'=c->>'upload' AND command IN ('select','update'); END IF;
            RETURN tab IN ('organizations','customers','generic_json_records') AND command IN ('select','insert','update');
        END IF;
        IF tab='audit_events' THEN RETURN command='select' OR
            (command='insert' AND r->>'actor_id'=c->>'sub' AND r->>'action' NOT LIKE 'platform.%'); END IF;
        IF tab='organizations' THEN RETURN command='select' OR
            (command='update' AND a->>'role' IN ('owner','admin')); END IF;
        RETURN true; -- Runtime application CRUD, confined to the verified tenant AND organization above.
    END IF;
    IF session_user='hanuram_runtime' AND p='webhook.scope' THEN
        scoped:=t=(c->>'tenant')::integer AND o=(c->>'org')::integer;
        IF NOT coalesce(scoped,false) THEN RETURN false; END IF;
        IF tab='whatsapp_bulk_jobs' THEN RETURN command IN ('select','update')
            AND r->'audience_payload'->>'sender_phone_number_id'=c->>'phone'; END IF;
        IF tab='message_records' THEN RETURN command IN ('select','update') AND r->>'sender_phone_id'=c->>'phone'; END IF;
        IF tab='contact_consents' THEN RETURN command IN ('select','insert','update'); END IF;
        IF tab='consent_events' THEN RETURN command='insert' AND NOT (r->>'opted_in')::boolean
            AND r->>'source'='whatsapp_inbound' AND r->>'actor_id' IS NULL; END IF;
        RETURN false;
    END IF;
    IF session_user='hanuram_control' AND p LIKE 'staff.%' THEN
        permission:=substring(p FROM 7);
        IF NOT hanuram_auth.permission(permission) THEN RETURN false; END IF;
        target:=t=(c->>'target_tenant')::integer AND (tab='tenants' OR o=(c->>'target_org')::integer);
        IF tab='audit_events' THEN
            IF command='select' THEN RETURN permission='audit.read' OR
                (permission='subscriptions.manage' AND r->>'resource_id'=c->>'resource'
                 AND r->'details'->>'request_id'=c->>'request_id' AND r->>'action' LIKE 'platform.subscription.%'); END IF;
            RETURN command='insert' AND r->>'actor_id'=c->>'sub'
                AND t=(c->>'tenant')::integer AND o=(c->>'org')::integer
                AND r->>'action'=c->>'action' AND r->>'resource_id'=c->>'resource';
        END IF;
        IF permission='subscriptions.read' THEN RETURN command='select' AND tab IN ('subscriptions','organizations'); END IF;
        IF permission='subscriptions.manage' THEN RETURN coalesce(target,false) AND
            ((tab='subscriptions' AND command IN ('select','insert','update')) OR
             (tab IN ('organizations','tenants') AND command IN ('select','update'))); END IF;
        IF permission='tenants.read' THEN RETURN command='select' AND tab='tenants'; END IF;
        IF permission='tenants.manage' THEN RETURN coalesce(target,false) AND tab='tenants' AND command IN ('select','update'); END IF;
        IF permission='onboarding.manage' THEN RETURN
            (tab='onboarding_requests' AND (command='select' OR (command='update' AND r->>'id'=c->>'resource')))
            OR (tab='whatsapp_connections' AND command='select' AND coalesce(target,false)); END IF;
        IF permission='usage.manage' THEN RETURN coalesce(target,false) AND
            ((tab='organizations' AND command='select') OR (tab='usage_entries' AND command IN ('select','insert'))); END IF;
    END IF;
    RETURN false;
END
$$;
ALTER FUNCTION hanuram_auth.allowed(text,text,jsonb) OWNER TO hanuram_identity_owner;
REVOKE ALL ON FUNCTION hanuram_auth.allowed(text,text,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION hanuram_auth.allowed(text,text,jsonb) TO hanuram_runtime,hanuram_control;
"""


def upgrade():
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT current_schema()")) != "public":
        raise RuntimeError("Authorization installation requires an explicit public-schema application database")
    for role in ['hanuram_runtime', 'hanuram_control', *OWNERS]:
        row = bind.execute(sa.text("SELECT rolsuper,rolbypassrls,rolcreaterole,rolcreatedb,rolcanlogin FROM pg_roles WHERE rolname=:role"), {'role': role}).first()
        if not row or any(row[:4]) or row.rolcanlogin != (role not in OWNERS):
            raise RuntimeError(f"Prepare restricted role {role} before this migration")
        if role not in OWNERS and bind.scalar(sa.text("SELECT count(*) FROM pg_roles WHERE rolname<>:role AND pg_has_role(:role,oid,'MEMBER')"), {'role':role}):
            raise RuntimeError('Application logins must not have inherited or assumable group roles')
        if role in OWNERS and not bind.scalar(sa.text("SELECT pg_has_role(current_user,:role,'SET')"), {'role': role}):
            raise RuntimeError(f"Operator needs temporary SET ROLE authority for {role}")
        if role in OWNERS:
            for login in ('hanuram_runtime', 'hanuram_control'):
                if bind.scalar(sa.text("SELECT pg_has_role(:login,:role,'MEMBER')"), {'login': login, 'role': role}):
                    raise RuntimeError("Application logins must not be members of function owner roles")
    crypto = bind.scalar(sa.text("SELECT n.nspname FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='pgcrypto'"))
    if crypto != 'hanuram_crypto':
        raise RuntimeError("Operator must install pgcrypto in the trusted hanuram_crypto schema first")
    op.execute(sa.text((Path(__file__).parents[1] / 'authorization' / 'f91c320ab006.sql').read_text()))
    op.execute(sa.text(ALLOWED_SQL))
    # Erase prior broad grants. No application login owns a protected table.
    op.execute('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM hanuram_runtime,hanuram_control')
    op.execute('REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM hanuram_runtime,hanuram_control')
    op.execute('REVOKE CREATE ON SCHEMA public FROM PUBLIC,hanuram_runtime,hanuram_control')
    op.execute('GRANT USAGE ON SCHEMA public TO hanuram_runtime,hanuram_control,hanuram_identity_owner,hanuram_staff_owner,hanuram_jobs_owner')
    if bind.scalar(sa.text("SELECT to_regclass('public.alembic_version')")):
        op.execute('GRANT SELECT ON public.alembic_version TO hanuram_runtime,hanuram_control')
    op.execute('GRANT SELECT,INSERT,UPDATE ON users TO hanuram_control')
    op.execute('GRANT SELECT,UPDATE ON organizations,tenants,subscriptions,onboarding_requests TO hanuram_control')
    op.execute('GRANT INSERT ON subscriptions TO hanuram_control')
    op.execute('GRANT SELECT,INSERT ON audit_events,usage_entries,subscription_plans TO hanuram_control')
    op.execute('GRANT SELECT ON platform_staff TO hanuram_control')
    op.execute('GRANT SELECT (id,tenant_id,organization_id,phone_number_id,waba_id,token_expires_at) ON whatsapp_connections TO hanuram_control')
    op.execute('GRANT USAGE ON SEQUENCE users_id_seq TO hanuram_control')
    for table in TABLES:
        owner = bind.scalar(sa.text("SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid=to_regclass(:name)"), {'name': 'public.' + table})
        if owner in ['hanuram_runtime', 'hanuram_control', *OWNERS]:
            raise RuntimeError("Application and function roles must not own protected application tables")
        op.execute(f'ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY')
        op.execute(f'DROP POLICY hanuram_tenant_scope ON public.{table}')
        for command in ['select', 'insert', 'update', 'delete']:
            expression = f"hanuram_auth.allowed('{table}','{command}',to_jsonb({table}))"
            clause = (f'WITH CHECK ({expression})' if command == 'insert' else
                      f'USING ({expression}) WITH CHECK ({expression})' if command == 'update' else f'USING ({expression})')
            op.execute(f'CREATE POLICY verified_{command} ON public.{table} FOR {command.upper()} TO hanuram_runtime,hanuram_control {clause}')
        grants = 'SELECT' if table in ['tenants', 'users', 'subscriptions', 'usage_entries', 'saas_invoices'] else (
            'SELECT,INSERT' if table in ['audit_events', 'consent_events'] else 'SELECT,INSERT,UPDATE,DELETE')
        op.execute(f'GRANT {grants} ON public.{table} TO hanuram_runtime')
        serial = bind.scalar(sa.text("SELECT pg_get_serial_sequence(:table,'id')"), {'table': 'public.' + table})
        if serial and 'INSERT' in grants:
            # pg_get_serial_sequence returns a catalog identifier, not user input.
            op.execute(f'GRANT USAGE ON SEQUENCE {serial} TO hanuram_runtime')
    for table in ['platform_staff', 'subscription_plans']:
        op.execute(f'ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY')
        for command in ['select', 'insert']:
            expression = f"hanuram_auth.allowed('{table}','{command}',to_jsonb({table}))"
            clause = 'WITH CHECK' if command == 'insert' else 'USING'
            op.execute(f'CREATE POLICY verified_{command} ON public.{table} FOR {command.upper()} TO hanuram_runtime,hanuram_control {clause} ({expression})')
    op.execute('GRANT SELECT ON subscription_plans TO hanuram_runtime')
    op.execute('CREATE POLICY shared_plan_read ON subscription_plans FOR SELECT TO hanuram_runtime USING (true)')
    # Owner policies are exact-subject or exact-purpose, never owner-wide bypass.
    op.execute('GRANT SELECT,INSERT,UPDATE ON tenants,users,organizations,business_profiles TO hanuram_identity_owner')
    op.execute('GRANT SELECT,UPDATE ON platform_staff TO hanuram_identity_owner')
    op.execute('GRANT SELECT ON data_uploads,whatsapp_bulk_jobs,whatsapp_connections TO hanuram_identity_owner')
    for sequence in ['tenants_id_seq', 'users_id_seq', 'organizations_id_seq', 'business_profiles_id_seq']:
        op.execute(f'GRANT USAGE ON SEQUENCE {sequence} TO hanuram_identity_owner')
    c = 'hanuram_auth.context()'
    for table, predicate in {
        'users': f"id=({c}->>'sub')::integer OR ({c}->>'purpose'='identity.email' AND email={c}->>'email')",
        'organizations': f"id=({c}->>'org')::integer OR id=(SELECT organization_id FROM public.users WHERE id=({c}->>'sub')::integer)",
        'tenants': f"id=({c}->>'tenant')::integer",
        'business_profiles': f"tenant_id=({c}->>'tenant')::integer AND organization_id=({c}->>'org')::integer",
        'platform_staff': f"user_id=({c}->>'sub')::integer",
        'data_uploads': f"{c}->>'purpose'='upload.scope' AND id=({c}->>'upload')::integer",
        'whatsapp_bulk_jobs': f"{c}->>'purpose'='job.scope' AND id=({c}->>'job')::integer",
        'whatsapp_connections': f"{c}->>'purpose'='webhook.scope' AND phone_number_id={c}->>'phone' AND waba_id={c}->>'waba'",
    }.items():
        op.execute(f'CREATE POLICY identity_lookup ON public.{table} FOR SELECT TO hanuram_identity_owner USING ({predicate})')
    for table, predicate in {
        'tenants': f"id=({c}->>'tenant')::integer", 'users': f"id=({c}->>'sub')::integer AND role='owner'",
        'organizations': f"id=({c}->>'org')::integer AND tenant_id=({c}->>'tenant')::integer AND owner_id=({c}->>'sub')::integer",
        'business_profiles': f"tenant_id=({c}->>'tenant')::integer AND organization_id=({c}->>'org')::integer",
    }.items():
        op.execute(f"CREATE POLICY identity_register ON public.{table} FOR INSERT TO hanuram_identity_owner WITH CHECK ({c}->>'purpose'='register' AND {predicate})")
    op.execute(f"CREATE POLICY identity_user_update ON users FOR UPDATE TO hanuram_identity_owner USING (id=({c}->>'sub')::integer AND {c}->>'purpose' IN ('register','staff.subscriptions.manage','staff.tenants.manage','staff.plans.manage','staff.onboarding.manage','staff.usage.manage','staff.audit.read','staff.subscriptions.read','staff.tenants.read')) WITH CHECK (id=({c}->>'sub')::integer)")
    op.execute(f"CREATE POLICY identity_staff_lock ON platform_staff FOR UPDATE TO hanuram_identity_owner USING (user_id=({c}->>'sub')::integer AND {c}->>'purpose' LIKE 'staff.%') WITH CHECK (user_id=({c}->>'sub')::integer)")
    op.execute('GRANT SELECT,UPDATE ON whatsapp_bulk_jobs TO hanuram_jobs_owner')
    op.execute('GRANT SELECT ON whatsapp_connections TO hanuram_jobs_owner')
    due = f"{c}->>'purpose'='job.claim' AND status IN ('scheduled','in_progress') AND scheduled_at<=statement_timestamp() AT TIME ZONE 'UTC' AND (({c}->>'job') IS NULL OR id=({c}->>'job')::integer)"
    op.execute(f'CREATE POLICY job_claim ON whatsapp_bulk_jobs TO hanuram_jobs_owner USING ({due}) WITH CHECK ({due})')
    op.execute('GRANT SELECT,UPDATE ON campaign_outbox TO hanuram_jobs_owner')
    outbox = f"{c}->>'purpose'='job.claim' AND {c}->>'transport'='celery' AND status IN ('pending','published') AND EXISTS(SELECT 1 FROM public.whatsapp_bulk_jobs b WHERE b.id=bulk_job_id AND b.tenant_id=campaign_outbox.tenant_id AND b.organization_id=campaign_outbox.organization_id)"
    op.execute(f'CREATE POLICY job_outbox_claim ON campaign_outbox TO hanuram_jobs_owner USING ({outbox}) WITH CHECK ({outbox})')
    op.execute(f"CREATE POLICY webhook_lookup ON whatsapp_connections FOR SELECT TO hanuram_jobs_owner USING ({c}->>'purpose'='webhook.lookup' AND phone_number_id={c}->>'phone' AND waba_id={c}->>'waba')")
    op.execute('GRANT SELECT ON tenants,subscriptions,onboarding_requests TO hanuram_staff_owner')
    for table in ['tenants', 'subscriptions', 'onboarding_requests']:
        op.execute(f"CREATE POLICY staff_overview ON {table} FOR SELECT TO hanuram_staff_owner USING ({c}->>'purpose'='staff.tenants.read' AND hanuram_auth.permission('tenants.read'))")


def downgrade():
    raise RuntimeError('Authorization rollback requires a reviewed database backup; never restore blanket control grants')
