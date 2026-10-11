CREATE TABLE hanuram_auth.staff_changes (
    pid integer NOT NULL, xid text NOT NULL, table_name text NOT NULL,
    resource text NOT NULL, actor_id integer NOT NULL, action text NOT NULL,
    before_row jsonb, after_row jsonb NOT NULL,
    PRIMARY KEY(pid,xid,table_name,resource)
);
ALTER TABLE hanuram_auth.staff_changes OWNER TO hanuram_staff_owner;
REVOKE ALL ON hanuram_auth.staff_changes FROM PUBLIC,hanuram_runtime,hanuram_control;
CREATE TABLE hanuram_auth.audit_receipts (pid integer NOT NULL,xid text NOT NULL,event_id text NOT NULL,PRIMARY KEY(pid,xid,event_id));
ALTER TABLE hanuram_auth.audit_receipts OWNER TO hanuram_staff_owner;
REVOKE ALL ON hanuram_auth.audit_receipts FROM PUBLIC,hanuram_runtime,hanuram_control;
CREATE FUNCTION hanuram_auth.audit_receipt() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,hanuram_auth,pg_temp AS $$
BEGIN
    INSERT INTO hanuram_auth.audit_receipts VALUES(pg_backend_pid(),txid_current()::text,NEW.id);
    RETURN NEW;
END $$;
ALTER FUNCTION hanuram_auth.audit_receipt() OWNER TO hanuram_staff_owner;
REVOKE ALL ON FUNCTION hanuram_auth.audit_receipt() FROM PUBLIC;

-- Guards prevent scoped database credentials from changing identity/ownership,
-- creating staff membership, or using webhook access to replace message content.
CREATE FUNCTION hanuram_auth.guard_row() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,hanuram_auth,pg_temp AS $$
DECLARE c jsonb:=hanuram_auth.context(); p text:=c->>'purpose'; oldrow jsonb; newrow jsonb:=to_jsonb(NEW); a jsonb;
BEGIN
    IF TG_OP='UPDATE' THEN
        oldrow:=to_jsonb(OLD);
        IF oldrow->'id' IS DISTINCT FROM newrow->'id' OR oldrow->'tenant_id' IS DISTINCT FROM newrow->'tenant_id'
            OR (TG_TABLE_NAME<>'users' AND oldrow->'organization_id' IS DISTINCT FROM newrow->'organization_id') THEN
            RAISE EXCEPTION 'Record identity and tenant ownership are immutable' USING ERRCODE='42501';
        END IF;
    END IF;
    IF TG_TABLE_NAME='users' THEN
        IF p='register' AND current_user='hanuram_identity_owner' THEN RETURN NEW; END IF;
        IF p IS DISTINCT FROM 'account' OR session_user<>'hanuram_control' THEN
            RAISE EXCEPTION 'Account authorization required' USING ERRCODE='42501';
        END IF;
        a:=hanuram_auth.subject();
        IF TG_OP='INSERT' THEN
            IF a->>'role' NOT IN ('owner','admin') OR NEW.role='owner' OR NEW.tenant_id<>(c->>'tenant')::integer
                OR NEW.organization_id<>(c->>'org')::integer THEN
                RAISE EXCEPTION 'Member creation denied' USING ERRCODE='42501';
            END IF;
        ELSE
            IF OLD.organization_id IS DISTINCT FROM NEW.organization_id OR OLD.tenant_code IS DISTINCT FROM NEW.tenant_code THEN
                RAISE EXCEPTION 'User ownership is immutable' USING ERRCODE='42501';
            END IF;
            IF OLD.id=(c->>'sub')::integer THEN
                IF (oldrow-ARRAY['name','phone','password','password_changed_at','last_login','updated_at'])
                    IS DISTINCT FROM (newrow-ARRAY['name','phone','password','password_changed_at','last_login','updated_at']) THEN
                    RAISE EXCEPTION 'Self privilege changes are forbidden' USING ERRCODE='42501';
                END IF;
            ELSIF a->>'role' NOT IN ('owner','admin') OR OLD.role='owner' OR NEW.role='owner' THEN
                RAISE EXCEPTION 'Member privilege change denied' USING ERRCODE='42501';
            END IF;
        END IF;
    ELSIF TG_TABLE_NAME='organizations' AND TG_OP='UPDATE' THEN
        IF OLD.owner_id IS DISTINCT FROM NEW.owner_id OR OLD.tenant_code IS DISTINCT FROM NEW.tenant_code
            OR p='staff.subscriptions.manage' THEN
            RAISE EXCEPTION 'Organization ownership cannot change through this operation' USING ERRCODE='42501';
        END IF;
    ELSIF p='webhook.scope' THEN
        IF TG_TABLE_NAME='whatsapp_bulk_jobs' AND (oldrow-ARRAY['recipients_summary','stats','status','updated_at'])
            IS DISTINCT FROM (newrow-ARRAY['recipients_summary','stats','status','updated_at']) THEN
            RAISE EXCEPTION 'Webhook cannot replace campaign content' USING ERRCODE='42501';
        ELSIF TG_TABLE_NAME='message_records' AND (oldrow-ARRAY['status','status_timestamp','updated_at'])
            IS DISTINCT FROM (newrow-ARRAY['status','status_timestamp','updated_at']) THEN
            RAISE EXCEPTION 'Webhook cannot replace message identity' USING ERRCODE='42501';
        ELSIF TG_TABLE_NAME='contact_consents' THEN
            IF NEW.opted_in AND (TG_OP='INSERT' OR NOT OLD.opted_in) THEN
                RAISE EXCEPTION 'Webhook cannot manufacture opt-in' USING ERRCODE='42501';
            END IF;
        END IF;
    END IF;
    RETURN NEW;
END $$;
ALTER FUNCTION hanuram_auth.guard_row() OWNER TO hanuram_identity_owner;
REVOKE ALL ON FUNCTION hanuram_auth.guard_row() FROM PUBLIC;

CREATE FUNCTION hanuram_auth.record_staff_change() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,hanuram_auth,pg_temp AS $$
DECLARE c jsonb:=hanuram_auth.context(); p text:=c->>'purpose'; before_row jsonb; data jsonb:=c->'operation_payload'; stamp timestamptz:=clock_timestamp();
BEGIN
    IF session_user <> 'hanuram_control' OR p NOT LIKE 'staff.%' THEN
        RAISE EXCEPTION 'Explicit staff mutation authority required' USING ERRCODE='42501';
    END IF;
    IF TG_OP='UPDATE' THEN before_row:=to_jsonb(OLD); END IF;
    IF c->>'resource' IS NULL OR c->>'action' IS NULL THEN
        RAISE EXCEPTION 'Staff audit resource required' USING ERRCODE='42501';
    END IF;
    IF TG_TABLE_NAME='subscriptions' THEN
        IF p<>'staff.subscriptions.manage' OR (c->>'request_id')::uuid IS NULL
            OR length(btrim(coalesce(c->>'reason',''))) NOT BETWEEN 1 AND 500
            OR c->>'fingerprint' IS NULL THEN
            RAISE EXCEPTION 'Subscription mutation metadata required' USING ERRCODE='42501';
        END IF;
        IF NEW.tenant_id IS DISTINCT FROM (c->>'target_tenant')::integer OR NEW.organization_id IS DISTINCT FROM (c->>'target_org')::integer
            OR c->>'resource' IS DISTINCT FROM 'organization:'||NEW.organization_id::text THEN
            RAISE EXCEPTION 'Subscription target mismatch' USING ERRCODE='42501';
        END IF;
        IF TG_OP='UPDATE' AND (OLD.id IS DISTINCT FROM NEW.id OR OLD.tenant_id IS DISTINCT FROM NEW.tenant_id
            OR OLD.organization_id IS DISTINCT FROM NEW.organization_id) THEN
            RAISE EXCEPTION 'Subscription ownership is immutable' USING ERRCODE='42501';
        END IF;
        IF c->>'operation'='assign' THEN
            IF NEW.plan_id IS DISTINCT FROM data->>'plan_id' OR NEW.status<>'active' OR NEW.cancel_at_period_end
                OR NEW.current_start IS DISTINCT FROM (data->>'current_start')::timestamptz
                OR NEW.current_end IS DISTINCT FROM (data->>'current_end')::timestamptz
                OR NEW.current_start IS NULL OR NEW.current_end IS NULL
                OR NEW.current_end<=stamp OR NEW.current_start>=NEW.current_end THEN
                RAISE EXCEPTION 'Invalid assignment' USING ERRCODE='42501';
            END IF;
        ELSIF c->>'operation'='renew' THEN
            IF TG_OP<>'UPDATE' OR (data->>'days')::integer NOT BETWEEN 1 AND 3660 OR OLD.status NOT IN ('active','expired','completed')
                OR OLD.current_start IS NULL OR OLD.current_end IS NULL OR OLD.current_start>=OLD.current_end
                OR NEW.plan_id IS DISTINCT FROM OLD.plan_id OR NEW.status<>'active' OR NEW.cancel_at_period_end
                OR (OLD.current_end>stamp AND NEW.current_start IS DISTINCT FROM OLD.current_start)
                OR (OLD.current_end<=stamp AND (NEW.current_start IS NULL OR abs(extract(epoch FROM NEW.current_start-stamp))>5))
                OR abs(extract(epoch FROM NEW.current_end-(greatest(OLD.current_end,stamp)+(data->>'days')::integer*interval '1 day'))) > 5 THEN
                RAISE EXCEPTION 'Invalid renewal' USING ERRCODE='42501';
            END IF;
        ELSIF c->>'operation'='cancel' THEN
            IF TG_OP<>'UPDATE' OR NEW.plan_id IS DISTINCT FROM OLD.plan_id
                OR NEW.current_start IS DISTINCT FROM OLD.current_start OR NEW.current_end IS DISTINCT FROM OLD.current_end
                OR ((data->>'at_period_end')::boolean AND
                    (OLD.status<>'active' OR OLD.current_end IS NULL OR OLD.current_end<=stamp OR NEW.status<>OLD.status OR NOT NEW.cancel_at_period_end))
                OR (NOT (data->>'at_period_end')::boolean AND (NEW.status<>'cancelled' OR NEW.cancel_at_period_end)) THEN
                RAISE EXCEPTION 'Invalid cancellation' USING ERRCODE='42501';
            END IF;
        ELSE RAISE EXCEPTION 'Unknown subscription operation' USING ERRCODE='42501'; END IF;
    ELSIF TG_TABLE_NAME='tenants' THEN
        IF (to_jsonb(OLD)-ARRAY['is_active','updated_at']) IS DISTINCT FROM (to_jsonb(NEW)-ARRAY['is_active','updated_at'])
            OR (NEW.id=(c->>'tenant')::integer AND NOT NEW.is_active) THEN
            RAISE EXCEPTION 'Invalid tenant status mutation' USING ERRCODE='42501';
        END IF;
    END IF;
    INSERT INTO hanuram_auth.staff_changes VALUES(pg_backend_pid(),txid_current()::text,TG_TABLE_NAME,c->>'resource',
        (c->>'sub')::integer,c->>'action',before_row,to_jsonb(NEW))
      ON CONFLICT(pid,xid,table_name,resource) DO UPDATE SET after_row=excluded.after_row;
    RETURN NEW;
END $$;
ALTER FUNCTION hanuram_auth.record_staff_change() OWNER TO hanuram_staff_owner;
REVOKE ALL ON FUNCTION hanuram_auth.record_staff_change() FROM PUBLIC;

CREATE FUNCTION hanuram_auth.require_staff_audit() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,hanuram_auth,pg_temp AS $$
DECLARE change hanuram_auth.staff_changes%ROWTYPE; event public.audit_events%ROWTYPE; c jsonb:=hanuram_auth.context();
BEGIN
    SELECT * INTO change FROM hanuram_auth.staff_changes WHERE pid=pg_backend_pid() AND xid=txid_current()::text
        AND table_name=TG_TABLE_NAME AND resource=c->>'resource';
    IF NOT FOUND THEN RAISE EXCEPTION 'Missing transactional staff change' USING ERRCODE='42501'; END IF;
    SELECT e.* INTO event FROM public.audit_events e JOIN hanuram_auth.audit_receipts r ON r.event_id=e.id
        WHERE r.pid=pg_backend_pid() AND r.xid=txid_current()::text
        AND e.actor_id=change.actor_id AND e.resource_id=change.resource
        AND e.action=change.action ORDER BY e.occurred_at DESC LIMIT 1;
    IF NOT FOUND THEN RAISE EXCEPTION 'Staff mutation requires atomic audit' USING ERRCODE='42501'; END IF;
    IF TG_TABLE_NAME='subscriptions' THEN
      IF (event.details->>'request_id' IS DISTINCT FROM c->>'request_id'
        OR event.details->>'fingerprint' IS DISTINCT FROM c->>'fingerprint'
        OR event.details->>'reason' IS DISTINCT FROM c->>'reason'
        OR (event.details->>'target_tenant')::integer IS DISTINCT FROM NEW.tenant_id
        OR (event.details->>'target_organization')::integer IS DISTINCT FROM NEW.organization_id
        OR event.details->'before'->>'id' IS DISTINCT FROM change.before_row->>'id'
        OR event.details->'before'->>'plan_id' IS DISTINCT FROM change.before_row->>'plan_id'
        OR event.details->'before'->>'status' IS DISTINCT FROM change.before_row->>'status'
        OR (event.details->'before'->>'current_start')::timestamptz IS DISTINCT FROM (change.before_row->>'current_start')::timestamptz
        OR (event.details->'before'->>'current_end')::timestamptz IS DISTINCT FROM (change.before_row->>'current_end')::timestamptz
        OR (event.details->'before'->>'cancel_at_period_end')::boolean IS DISTINCT FROM (change.before_row->>'cancel_at_period_end')::boolean
        OR event.details->'after'->>'id' IS DISTINCT FROM NEW.id
        OR event.details->'after'->>'plan_id' IS DISTINCT FROM NEW.plan_id
        OR event.details->'after'->>'status' IS DISTINCT FROM NEW.status
        OR (event.details->'after'->>'current_start')::timestamptz IS DISTINCT FROM NEW.current_start
        OR (event.details->'after'->>'current_end')::timestamptz IS DISTINCT FROM NEW.current_end
        OR (event.details->'after'->>'cancel_at_period_end')::boolean IS DISTINCT FROM NEW.cancel_at_period_end) THEN
        RAISE EXCEPTION 'Subscription audit does not describe mutation' USING ERRCODE='42501';
      END IF;
    END IF;
    RETURN NULL;
END $$;
ALTER FUNCTION hanuram_auth.require_staff_audit() OWNER TO hanuram_staff_owner;
REVOKE ALL ON FUNCTION hanuram_auth.require_staff_audit() FROM PUBLIC;

CREATE TABLE hanuram_auth.operators (role_oid oid PRIMARY KEY);
ALTER TABLE hanuram_auth.operators OWNER TO hanuram_staff_owner;
REVOKE ALL ON hanuram_auth.operators FROM PUBLIC,hanuram_runtime,hanuram_control;
-- Captures the separate migration operator, never an application login.
INSERT INTO hanuram_auth.operators SELECT oid FROM pg_catalog.pg_roles WHERE rolname=current_user;
GRANT SELECT,INSERT,UPDATE ON hanuram_auth.contexts TO hanuram_staff_owner;

CREATE FUNCTION hanuram_auth.operator_staff(email text, permissions jsonb, apply boolean DEFAULT false) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,hanuram_auth,pg_temp AS $$
DECLARE u public.users%ROWTYPE; c jsonb; stamp timestamp:=clock_timestamp() AT TIME ZONE 'UTC';
BEGIN
    IF NOT EXISTS(SELECT 1 FROM hanuram_auth.operators WHERE role_oid=(SELECT oid FROM pg_roles WHERE rolname=session_user)) THEN
        RAISE EXCEPTION 'Offline provisioning operator required' USING ERRCODE='42501';
    END IF;
    IF jsonb_typeof(permissions)<>'array' OR jsonb_array_length(permissions)=0 OR EXISTS(
        SELECT 1 FROM jsonb_array_elements_text(permissions) p WHERE p NOT IN
        ('tenants.read','tenants.manage','plans.manage','subscriptions.read','subscriptions.manage','onboarding.manage','usage.manage','audit.read')) THEN
        RAISE EXCEPTION 'Invalid staff permissions' USING ERRCODE='22023';
    END IF;
    c:=jsonb_build_object('purpose','operator.staff','email',lower(btrim(email)));
    INSERT INTO hanuram_auth.contexts VALUES(pg_backend_pid(),txid_current()::text,session_user,c,clock_timestamp()+interval '90 seconds')
        ON CONFLICT(pid,xid) DO UPDATE SET claims=excluded.claims,expires=excluded.expires;
    SELECT * INTO u FROM public.users WHERE users.email=lower(btrim(operator_staff.email)) AND is_active FOR SHARE;
    IF NOT FOUND OR u.organization_id IS NULL OR u.tenant_id IS NULL THEN
        RAISE EXCEPTION 'Existing active workspace user required' USING ERRCODE='22023';
    END IF;
    c:=c||jsonb_build_object('sub',u.id,'tenant',u.tenant_id,'org',u.organization_id);
    UPDATE hanuram_auth.contexts SET claims=c WHERE pid=pg_backend_pid() AND xid=txid_current()::text;
    IF apply THEN
        INSERT INTO public.platform_staff VALUES(u.id,true,permissions,stamp,stamp)
            ON CONFLICT(user_id) DO UPDATE SET is_active=true,permissions=excluded.permissions,updated_at=excluded.updated_at;
        INSERT INTO public.audit_events(id,tenant_id,organization_id,actor_id,action,resource_id,details,occurred_at)
            VALUES(gen_random_uuid()::text,u.tenant_id,u.organization_id,u.id,'platform.staff.permissions.updated',u.id::text,
                jsonb_build_object('permissions',permissions,'operator_role',session_user),clock_timestamp());
    END IF;
    RETURN jsonb_build_object('user_id',u.id,'permissions',permissions,'applied',apply);
END $$;
ALTER FUNCTION hanuram_auth.operator_staff(text,jsonb,boolean) OWNER TO hanuram_staff_owner;
REVOKE ALL ON FUNCTION hanuram_auth.operator_staff(text,jsonb,boolean) FROM PUBLIC;
