CREATE OR REPLACE FUNCTION hanuram_auth.guard_row() RETURNS trigger
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
        ELSIF TG_TABLE_NAME='message_records' AND (oldrow-ARRAY['status','status_timestamp','delivery_details','updated_at'])
            IS DISTINCT FROM (newrow-ARRAY['status','status_timestamp','delivery_details','updated_at']) THEN
            RAISE EXCEPTION 'Webhook cannot replace message identity' USING ERRCODE='42501';
        ELSIF TG_TABLE_NAME='contact_consents' THEN
            IF NEW.opted_in AND (TG_OP='INSERT' OR NOT OLD.opted_in) THEN
                RAISE EXCEPTION 'Webhook cannot manufacture opt-in' USING ERRCODE='42501';
            END IF;
        END IF;
    END IF;
    RETURN NEW;
END $$;
