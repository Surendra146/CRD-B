-- Immutable SQL asset belonging to revision f91c320ab006.
CREATE SCHEMA hanuram_auth AUTHORIZATION hanuram_identity_owner;
REVOKE ALL ON SCHEMA hanuram_auth FROM PUBLIC;
GRANT USAGE ON SCHEMA hanuram_auth TO hanuram_runtime, hanuram_control,
    hanuram_staff_owner, hanuram_jobs_owner;
GRANT CREATE ON SCHEMA hanuram_auth TO hanuram_staff_owner, hanuram_jobs_owner;

CREATE TABLE hanuram_auth.signing_keys (
    purpose text PRIMARY KEY CHECK (purpose IN ('identity','staff','jobs')),
    secret text NOT NULL CHECK (length(secret) >= 32)
);
ALTER TABLE hanuram_auth.signing_keys OWNER TO hanuram_identity_owner;
REVOKE ALL ON hanuram_auth.signing_keys FROM PUBLIC, hanuram_runtime, hanuram_control;
CREATE TABLE hanuram_auth.installation (id uuid PRIMARY KEY);
INSERT INTO hanuram_auth.installation VALUES(gen_random_uuid());
ALTER TABLE hanuram_auth.installation OWNER TO hanuram_identity_owner;
REVOKE ALL ON hanuram_auth.installation FROM PUBLIC,hanuram_runtime,hanuram_control;
CREATE FUNCTION hanuram_auth.installation_id() RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,hanuram_auth,pg_temp AS $$
    SELECT id FROM hanuram_auth.installation
$$;
CREATE FUNCTION hanuram_auth.check_key(kind text, signature text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,hanuram_auth,pg_temp AS $$
    SELECT coalesce((SELECT signature=encode(hanuram_crypto.hmac(convert_to(
        hanuram_auth.installation_id()::text||':'||session_user::text||':'||pg_backend_pid()::text||':'||txid_current()::text,'UTF8'),
        convert_to(k.secret,'UTF8'),'sha256'),'hex') FROM hanuram_auth.signing_keys k WHERE k.purpose=kind),false)
$$;
CREATE TABLE hanuram_auth.contexts (
    pid integer NOT NULL, xid text NOT NULL, login name NOT NULL,
    claims jsonb NOT NULL, expires timestamptz NOT NULL, PRIMARY KEY(pid,xid)
);
ALTER TABLE hanuram_auth.contexts OWNER TO hanuram_identity_owner;
REVOKE ALL ON hanuram_auth.contexts FROM PUBLIC, hanuram_runtime, hanuram_control;
CREATE TABLE hanuram_auth.job_leases (
    job_id integer PRIMARY KEY REFERENCES public.whatsapp_bulk_jobs(id),
    lease uuid NOT NULL, expires timestamptz NOT NULL
);
ALTER TABLE hanuram_auth.job_leases OWNER TO hanuram_jobs_owner;
REVOKE ALL ON hanuram_auth.job_leases FROM PUBLIC, hanuram_runtime, hanuram_control;
GRANT SELECT,UPDATE ON hanuram_auth.job_leases TO hanuram_identity_owner;

CREATE FUNCTION hanuram_auth.context() RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, hanuram_auth, pg_temp AS $$
    SELECT coalesce((SELECT claims FROM hanuram_auth.contexts
        WHERE pid=pg_backend_pid() AND xid=txid_current()::text
        AND login=session_user AND expires > statement_timestamp()), '{}'::jsonb)
$$;

-- These queries are governed by the identity-owner's exact-subject policies.
-- Their owner is NOT a protected-table owner and has NO bypass attribute.
CREATE FUNCTION hanuram_auth.subject() RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, hanuram_auth, pg_temp AS $$
    SELECT coalesce((SELECT jsonb_build_object(
        'id',u.id,'tenant',u.tenant_id,'org',u.organization_id,'role',u.role,'modules',u.allowed_modules,
        'active',u.is_active AND t.is_active AND o.tenant_id=u.tenant_id,
        'owner',o.owner_id=u.id,'changed',extract(epoch FROM u.password_changed_at AT TIME ZONE 'UTC'))
      FROM public.users u JOIN public.organizations o ON o.id=u.organization_id
      JOIN public.tenants t ON t.id=u.tenant_id
      WHERE u.id=(hanuram_auth.context()->>'sub')::integer), '{}'::jsonb)
$$;

CREATE FUNCTION hanuram_auth.active_subject() RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, hanuram_auth, pg_temp AS $$
    SELECT coalesce((hanuram_auth.subject()->>'active')::boolean,false)
      AND coalesce((hanuram_auth.subject()->>'tenant')::integer=(hanuram_auth.context()->>'tenant')::integer,false)
      AND (hanuram_auth.context()->>'iat' IS NULL OR
           coalesce((hanuram_auth.subject()->>'changed')::numeric < (hanuram_auth.context()->>'iat')::numeric,true))
      AND ((hanuram_auth.subject()->>'role') <> 'owner' OR (hanuram_auth.subject()->>'owner')::boolean)
$$;

CREATE FUNCTION hanuram_auth.permission(wanted text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, hanuram_auth, pg_temp AS $$
    SELECT hanuram_auth.active_subject() AND EXISTS (
        SELECT 1 FROM public.platform_staff s
        WHERE s.user_id=(hanuram_auth.context()->>'sub')::integer
          AND s.is_active AND s.permissions ? wanted)
$$;

CREATE FUNCTION hanuram_auth.establish(payload text, signature text) RETURNS void
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, hanuram_auth, pg_temp AS $$
DECLARE c jsonb; previous jsonb; secret text; expected_key text; purpose text; subject jsonb;
BEGIN
    IF session_user NOT IN ('hanuram_runtime','hanuram_control') THEN
        RAISE EXCEPTION 'Application login required' USING ERRCODE='42501';
    END IF;
    c := payload::jsonb; purpose := c->>'purpose';
    expected_key := CASE WHEN purpose LIKE 'staff.%' THEN 'staff'
        WHEN purpose LIKE 'job.%' OR purpose LIKE 'upload.%' OR purpose LIKE 'webhook.%' THEN 'jobs'
        ELSE 'identity' END;
    SELECT k.secret INTO secret FROM hanuram_auth.signing_keys k WHERE k.purpose=expected_key;
    IF secret IS NULL OR c->>'key' IS DISTINCT FROM expected_key
       OR signature IS DISTINCT FROM encode(hanuram_crypto.hmac(convert_to(payload,'UTF8'),convert_to(secret,'UTF8'),'sha256'),'hex')
       OR c->>'aud' IS DISTINCT FROM 'hanuram-postgres-v1'
       OR c->>'installation' IS DISTINCT FROM hanuram_auth.installation_id()::text
       OR c->>'login' IS DISTINCT FROM session_user::text
       OR (c->>'pid')::integer IS DISTINCT FROM pg_backend_pid()
       OR c->>'xid' IS DISTINCT FROM txid_current()::text
       OR (c->>'exp')::numeric IS NULL
       OR to_timestamp((c->>'exp')::double precision) <= clock_timestamp()
       OR to_timestamp((c->>'exp')::double precision) > clock_timestamp()+interval '95 seconds' THEN
        RAISE EXCEPTION 'Invalid transaction assertion' USING ERRCODE='42501';
    END IF;
    IF NOT ((session_user='hanuram_runtime' AND purpose IN ('tenant','job.scope','upload.scope','webhook.scope'))
        OR (session_user='hanuram_control' AND (purpose IN ('identity.user','identity.email','register','account','job.claim','webhook.lookup')
            OR purpose IN ('staff.tenants.read','staff.tenants.manage','staff.plans.manage',
              'staff.subscriptions.read','staff.subscriptions.manage','staff.onboarding.manage','staff.usage.manage','staff.audit.read')))) THEN
        RAISE EXCEPTION 'Purpose unavailable to caller' USING ERRCODE='42501';
    END IF;
    previous := hanuram_auth.context();
    IF previous->>'sub' IS NOT NULL AND c->>'sub' IS DISTINCT FROM previous->>'sub' THEN
        RAISE EXCEPTION 'Actor cannot change inside a transaction' USING ERRCODE='42501';
    END IF;
    DELETE FROM hanuram_auth.contexts WHERE expires < clock_timestamp()-interval '5 minutes';
    INSERT INTO hanuram_auth.contexts VALUES(pg_backend_pid(),txid_current()::text,session_user,c,to_timestamp((c->>'exp')::double precision))
        ON CONFLICT(pid,xid) DO UPDATE SET claims=excluded.claims, expires=excluded.expires;
    IF purpose IN ('tenant','account','identity.user','job.scope','upload.scope') OR purpose LIKE 'staff.%' THEN
        IF NOT hanuram_auth.active_subject() THEN
            RAISE EXCEPTION 'Inactive or mismatched subject' USING ERRCODE='42501';
        END IF;
        subject := hanuram_auth.subject();
        IF purpose <> 'identity.user' AND (subject->>'org')::integer IS DISTINCT FROM (c->>'org')::integer THEN
            RAISE EXCEPTION 'Organization does not belong to subject' USING ERRCODE='42501';
        END IF;
        IF purpose IN ('identity.user','tenant','account') OR purpose LIKE 'staff.%' THEN
            IF c->>'iat' IS NULL OR (c->>'iat')::numeric > extract(epoch FROM clock_timestamp())+5 THEN
                RAISE EXCEPTION 'Verified token issue time required' USING ERRCODE='42501';
            END IF;
        END IF;
    END IF;
    IF purpose LIKE 'staff.%' THEN
        -- Hold the actor and membership during the whole staff transaction.
        PERFORM 1 FROM public.users WHERE id=(c->>'sub')::integer FOR SHARE;
        PERFORM 1 FROM public.platform_staff WHERE user_id=(c->>'sub')::integer FOR SHARE;
        IF NOT hanuram_auth.permission(substring(purpose FROM 7)) THEN
            RAISE EXCEPTION 'Staff permission denied' USING ERRCODE='42501';
        END IF;
    ELSIF purpose='upload.scope' THEN
        IF subject->>'role'='viewer' OR NOT EXISTS(SELECT 1 FROM public.data_uploads WHERE id=(c->>'upload')::integer
            AND tenant_id=(c->>'tenant')::integer
            AND organization_id=(c->>'org')::integer) THEN
            RAISE EXCEPTION 'Upload authorization denied' USING ERRCODE='42501';
        END IF;
    ELSIF purpose='job.scope' THEN
        IF subject->>'role'='viewer' OR (subject->>'role' NOT IN ('owner','admin') AND NOT (subject->'modules' ? 'whatsapp')) THEN
            RAISE EXCEPTION 'Campaign creator lacks messaging authority' USING ERRCODE='42501';
        END IF;
        IF NOT EXISTS(SELECT 1 FROM hanuram_auth.job_leases l JOIN public.whatsapp_bulk_jobs j ON j.id=l.job_id
            WHERE l.job_id=(c->>'job')::integer AND l.lease=(c->>'lease')::uuid AND l.expires>clock_timestamp()
            AND j.tenant_id=(c->>'tenant')::integer AND j.organization_id=(c->>'org')::integer
            AND j.created_by=(c->>'sub')::integer AND j.status IN ('scheduled','in_progress','paused','completed','failed')) THEN
            RAISE EXCEPTION 'Job lease invalid' USING ERRCODE='42501';
        END IF;
        UPDATE hanuram_auth.job_leases SET expires=clock_timestamp()+interval '30 minutes'
            WHERE job_id=(c->>'job')::integer AND lease=(c->>'lease')::uuid;
    ELSIF purpose='webhook.scope' THEN
        IF NOT EXISTS(SELECT 1 FROM public.whatsapp_connections WHERE phone_number_id=c->>'phone'
            AND waba_id=c->>'waba' AND tenant_id=(c->>'tenant')::integer AND organization_id=(c->>'org')::integer) THEN
            RAISE EXCEPTION 'Webhook sender mismatch' USING ERRCODE='42501';
        END IF;
    END IF;
END
$$;

CREATE FUNCTION hanuram_auth.register_account() RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, hanuram_auth, pg_temp AS $$
DECLARE c jsonb := hanuram_auth.context(); d jsonb; t integer; u integer; o integer; stamp timestamp := clock_timestamp() AT TIME ZONE 'UTC';
BEGIN
    IF session_user <> 'hanuram_control' OR c->>'purpose' IS DISTINCT FROM 'register' THEN
        RAISE EXCEPTION 'Registration capability required' USING ERRCODE='42501';
    END IF;
    d:=c->'data';
    IF coalesce(length(d->>'name'),0) NOT BETWEEN 1 AND 255 OR coalesce(length(d->>'company'),0) NOT BETWEEN 1 AND 255
        OR coalesce(length(d->>'email'),0) NOT BETWEEN 3 AND 255
        OR d->>'email' IS DISTINCT FROM lower(btrim(d->>'email'))
        OR coalesce(d->>'password','') !~ '^\$2[aby]\$'
        OR jsonb_typeof(d->'modules') IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'Invalid registration data' USING ERRCODE='22023';
    END IF;
    t:=nextval('public.tenants_id_seq'); u:=nextval('public.users_id_seq'); o:=nextval('public.organizations_id_seq');
    c:=c || jsonb_build_object('sub',u,'tenant',t,'org',o);
    UPDATE hanuram_auth.contexts SET claims=c WHERE pid=pg_backend_pid() AND xid=txid_current()::text;
    INSERT INTO public.tenants(id,name,subdomain,code,is_active,settings,created_at,updated_at)
        VALUES(t,d->>'company',d->>'identifier',d->>'code',true,'{}',stamp,stamp);
    INSERT INTO public.users(id,email,password,name,phone,phone_verified,company,role,allowed_modules,
        tenant_id,tenant_code,subscription,settings,is_active,created_at,updated_at)
        VALUES(u,d->>'email',d->>'password',d->>'name',d->>'phone',false,jsonb_build_object('name',d->>'company'),
          'owner',d->'modules',t,d->>'code','{}','{}',true,stamp,stamp);
    INSERT INTO public.organizations(id,name,slug,owner_id,tenant_id,tenant_code,members,custom_roles,settings,branding,limits,usage,created_at,updated_at)
        VALUES(o,d->>'company',d->>'identifier',u,t,d->>'code','[]','[]','{}','{}','{}','{}',stamp,stamp);
    UPDATE public.users SET organization_id=o WHERE id=u;
    INSERT INTO public.business_profiles(tenant_id,organization_id,legal_name,billing_email,phone,address,created_at,updated_at)
        VALUES(t,o,d->>'company',d->>'email',d->>'phone','{}',stamp,stamp);
    RETURN jsonb_build_object('user_id',u,'tenant_id',t,'organization_id',o);
END
$$;

CREATE FUNCTION hanuram_auth.webhook_connection()
RETURNS TABLE(id integer,tenant_id integer,organization_id integer,phone_number_id text,waba_id text)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, hanuram_auth, pg_temp AS $$
    SELECT w.id,w.tenant_id,w.organization_id,w.phone_number_id::text,w.waba_id::text FROM public.whatsapp_connections w
    WHERE session_user='hanuram_control' AND hanuram_auth.context()->>'purpose'='webhook.lookup'
      AND w.phone_number_id=hanuram_auth.context()->>'phone' AND w.waba_id=hanuram_auth.context()->>'waba'
$$;

CREATE FUNCTION hanuram_auth.claim_campaign(wanted integer DEFAULT NULL)
RETURNS TABLE(job_id integer,tenant_id integer,organization_id integer,actor_id integer,lease uuid)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, hanuram_auth, pg_temp AS $$
DECLARE j public.whatsapp_bulk_jobs%ROWTYPE; nonce uuid;
BEGIN
    IF session_user <> 'hanuram_control' OR hanuram_auth.context()->>'purpose' IS DISTINCT FROM 'job.claim'
        OR wanted IS DISTINCT FROM (hanuram_auth.context()->>'job')::integer
        OR coalesce(hanuram_auth.context()->>'transport','') NOT IN ('database','celery') THEN
        RAISE EXCEPTION 'Campaign claim capability required' USING ERRCODE='42501';
    END IF;
    SELECT b.* INTO j FROM public.whatsapp_bulk_jobs b
      WHERE b.status IN ('scheduled','in_progress') AND b.scheduled_at <= clock_timestamp() AT TIME ZONE 'UTC'
        AND (wanted IS NULL OR b.id=wanted)
        AND (hanuram_auth.context()->>'transport'='database' OR EXISTS(
            SELECT 1 FROM public.campaign_outbox o WHERE o.bulk_job_id=b.id
            AND o.tenant_id=b.tenant_id AND o.organization_id=b.organization_id
            AND o.status IN ('pending','published')))
        AND NOT EXISTS(SELECT 1 FROM hanuram_auth.job_leases l WHERE l.job_id=b.id AND l.expires>clock_timestamp())
      ORDER BY b.scheduled_at,b.id FOR UPDATE SKIP LOCKED LIMIT 1;
    IF NOT FOUND THEN RETURN; END IF;
    nonce:=gen_random_uuid();
    INSERT INTO hanuram_auth.job_leases VALUES(j.id,nonce,clock_timestamp()+interval '30 minutes')
      ON CONFLICT ON CONSTRAINT job_leases_pkey DO UPDATE SET lease=excluded.lease,expires=excluded.expires;
    IF hanuram_auth.context()->>'transport'='celery' THEN
        UPDATE public.campaign_outbox AS o SET status='published',last_attempt_at=clock_timestamp()
            WHERE o.bulk_job_id=j.id AND o.tenant_id=j.tenant_id AND o.organization_id=j.organization_id;
    END IF;
    RETURN QUERY SELECT j.id,j.tenant_id,j.organization_id,j.created_by,nonce;
END
$$;

CREATE FUNCTION hanuram_auth.platform_overview() RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, hanuram_auth, pg_temp AS $$
    SELECT CASE WHEN session_user='hanuram_control' AND hanuram_auth.context()->>'purpose'='staff.tenants.read'
        AND hanuram_auth.permission('tenants.read') THEN jsonb_build_object(
      'tenants',(SELECT count(*) FROM public.tenants),
      'active_subscriptions',(SELECT count(*) FROM public.subscriptions WHERE status='active'
          AND current_start<=statement_timestamp() AND current_end>statement_timestamp() AND current_start<current_end),
      'pending_onboarding',(SELECT count(*) FROM public.onboarding_requests WHERE status<>'ready')) END
$$;

-- All helpers and entry points use explicit owners; there is no PUBLIC execution.
ALTER FUNCTION hanuram_auth.context() OWNER TO hanuram_identity_owner;
ALTER FUNCTION hanuram_auth.installation_id() OWNER TO hanuram_identity_owner;
ALTER FUNCTION hanuram_auth.check_key(text,text) OWNER TO hanuram_identity_owner;
ALTER FUNCTION hanuram_auth.subject() OWNER TO hanuram_identity_owner;
ALTER FUNCTION hanuram_auth.active_subject() OWNER TO hanuram_identity_owner;
ALTER FUNCTION hanuram_auth.permission(text) OWNER TO hanuram_identity_owner;
ALTER FUNCTION hanuram_auth.establish(text,text) OWNER TO hanuram_identity_owner;
ALTER FUNCTION hanuram_auth.register_account() OWNER TO hanuram_identity_owner;
ALTER FUNCTION hanuram_auth.webhook_connection() OWNER TO hanuram_jobs_owner;
ALTER FUNCTION hanuram_auth.claim_campaign(integer) OWNER TO hanuram_jobs_owner;
ALTER FUNCTION hanuram_auth.platform_overview() OWNER TO hanuram_staff_owner;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA hanuram_auth FROM PUBLIC;
GRANT EXECUTE ON FUNCTION hanuram_auth.establish(text,text) TO hanuram_runtime,hanuram_control;
GRANT EXECUTE ON FUNCTION hanuram_auth.installation_id(),hanuram_auth.check_key(text,text) TO hanuram_runtime,hanuram_control;
GRANT EXECUTE ON FUNCTION hanuram_auth.context(),hanuram_auth.subject(),hanuram_auth.active_subject(),hanuram_auth.permission(text)
    TO hanuram_runtime,hanuram_control,hanuram_staff_owner,hanuram_jobs_owner;
GRANT EXECUTE ON FUNCTION hanuram_auth.register_account(),hanuram_auth.webhook_connection(),
    hanuram_auth.claim_campaign(integer),hanuram_auth.platform_overview() TO hanuram_control;
