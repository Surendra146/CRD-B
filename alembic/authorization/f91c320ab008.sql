-- Frozen SQL asset for revision f91c320ab008. Authentication checks are unchanged.
CREATE OR REPLACE FUNCTION hanuram_auth.establish(payload text, signature text) RETURNS void
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
    -- Retention is operator maintenance, never part of request authorization.
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

-- Bounded retention in a separate operator transaction. Locked rows are skipped.
CREATE FUNCTION hanuram_auth.prune_contexts(batch_size integer DEFAULT 1000) RETURNS integer
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, hanuram_auth, pg_temp AS $$
DECLARE removed integer;
BEGIN
    IF batch_size IS NULL OR batch_size NOT BETWEEN 1 AND 10000 THEN
        RAISE EXCEPTION 'Batch size must be between 1 and 10000' USING ERRCODE='22023';
    END IF;
    WITH candidates AS (
        SELECT pid, xid FROM hanuram_auth.contexts
        WHERE expires < statement_timestamp()-interval '5 minutes'
        ORDER BY expires, pid, xid
        LIMIT batch_size FOR UPDATE SKIP LOCKED
    )
    DELETE FROM hanuram_auth.contexts c USING candidates d
    WHERE c.pid=d.pid AND c.xid=d.xid;
    GET DIAGNOSTICS removed = ROW_COUNT;
    RETURN removed;
END
$$;
ALTER FUNCTION hanuram_auth.prune_contexts(integer) OWNER TO hanuram_identity_owner;
REVOKE ALL ON FUNCTION hanuram_auth.prune_contexts(integer)
    FROM PUBLIC, hanuram_runtime, hanuram_control;
