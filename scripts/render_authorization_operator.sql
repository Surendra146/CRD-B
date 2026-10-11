-- REVIEW AND RUN MANUALLY as the separate Render migration/operator login.
-- This does not contain passwords, signing keys, or application data.
-- PostgreSQL 18; both application logins must already exist.
BEGIN;
DO $$ BEGIN
    IF current_database() <> 'hanuram_production' THEN
        RAISE EXCEPTION 'Wrong database: expected hanuram_production, got %', current_database();
    END IF;
    IF current_setting('server_version_num')::integer NOT BETWEEN 180000 AND 189999 THEN
        RAISE EXCEPTION 'This operator script requires PostgreSQL 18';
    END IF;
END $$;
-- PostgreSQL grants ADMIN back to a non-superuser creator automatically. Ask
-- that creation-time grant to include SET, rather than granting ADMIN to self.
SET LOCAL createrole_self_grant = 'set,inherit';
DO $$
DECLARE name text;
BEGIN
    IF current_user IN ('hanuram_runtime','hanuram_control') THEN
        RAISE EXCEPTION 'Use the separate migration operator';
    END IF;
    IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=current_user AND (rolsuper OR rolbypassrls)) THEN
        RAISE EXCEPTION 'Use a NOSUPERUSER NOBYPASSRLS operator';
    END IF;
    IF session_user <> current_user THEN
        RAISE EXCEPTION 'Connect directly as the installation operator; do not SET ROLE';
    END IF;
    FOREACH name IN ARRAY ARRAY['hanuram_runtime','hanuram_control'] LOOP
        IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=name AND rolcanlogin
            AND NOT (rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb OR rolreplication)) THEN
            RAISE EXCEPTION 'Missing or elevated application login: %', name;
        END IF;
        IF EXISTS(SELECT 1 FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=name)) THEN
            RAISE EXCEPTION 'Application login has unexpected role memberships: %', name;
        END IF;
        IF EXISTS(SELECT 1 FROM pg_shdepend WHERE refclassid='pg_authid'::regclass
            AND refobjid=(SELECT oid FROM pg_roles WHERE rolname=name) AND deptype='o') THEN
            RAISE EXCEPTION 'Application login owns database objects: %', name;
        END IF;
        IF has_database_privilege(name,current_database(),'CREATE') OR EXISTS(
            SELECT 1 FROM pg_namespace WHERE nspname !~ '^pg_' AND nspname <> 'information_schema'
            AND has_schema_privilege(name,oid,'CREATE')) THEN
            RAISE EXCEPTION 'Application login has database/schema CREATE privileges: %', name;
        END IF;
    END LOOP;
    FOREACH name IN ARRAY ARRAY['hanuram_identity_owner','hanuram_staff_owner','hanuram_jobs_owner'] LOOP
        IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=name) THEN
            EXECUTE format('CREATE ROLE %I NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB NOREPLICATION NOINHERIT',name);
        END IF;
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=name AND (rolcanlogin OR rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb OR rolreplication OR rolinherit)) THEN
            RAISE EXCEPTION 'Unsafe function-owner role: %',name;
        END IF;
        -- Reject every outbound membership, even SET/INHERIT FALSE grants.
        -- Only this offline operator may be an explicit member of an owner role.
        IF EXISTS(SELECT 1 FROM pg_auth_members m WHERE
            m.member=(SELECT oid FROM pg_roles WHERE rolname=name) OR
            (m.roleid=(SELECT oid FROM pg_roles WHERE rolname=name)
             AND m.member<>(SELECT oid FROM pg_roles WHERE rolname=current_user))) THEN
            RAISE EXCEPTION 'Unsafe function-owner memberships: %', name;
        END IF;
        -- CREATEROLE does not imply SET ROLE on PostgreSQL 16+.
        IF NOT pg_has_role(current_user,name,'SET') THEN
            RAISE EXCEPTION 'Operator cannot assume existing owner role %; review its grant with its administrator',name;
        END IF;
        IF NOT pg_has_role(current_user,name,'USAGE') THEN
            -- Temporary installation membership; do not grant ADMIN to self.
            EXECUTE format('GRANT %I TO %I WITH INHERIT TRUE, SET TRUE',name,current_user);
        END IF;
    END LOOP;
END $$;
CREATE SCHEMA IF NOT EXISTS hanuram_crypto;
DO $$ BEGIN
    IF EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='hanuram_crypto'
        AND nspowner<>(SELECT oid FROM pg_roles WHERE rolname=current_user)) OR EXISTS(
        SELECT 1 FROM pg_namespace n, LATERAL aclexplode(n.nspacl) a
        WHERE n.nspname='hanuram_crypto' AND a.privilege_type='CREATE'
        AND a.grantee<>(SELECT oid FROM pg_roles WHERE rolname=current_user)) THEN
        RAISE EXCEPTION 'Unsafe hanuram_crypto ownership or CREATE grants';
    END IF;
END $$;
REVOKE ALL ON SCHEMA hanuram_crypto FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC,hanuram_runtime,hanuram_control;
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA hanuram_crypto;
DO $$ BEGIN
    IF (SELECT n.nspname FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='pgcrypto') <> 'hanuram_crypto' THEN
        RAISE EXCEPTION 'Existing pgcrypto is in another schema; review relocation separately';
    END IF;
END $$;
GRANT USAGE ON SCHEMA hanuram_crypto TO hanuram_identity_owner;
-- Trusted extension functions may be owned by PostgreSQL's bootstrap owner.
-- We do not require ownership of them: deny schema access to application logins
-- and grant only the private identity function owner schema USAGE.
REVOKE ALL ON SCHEMA hanuram_crypto FROM hanuram_runtime,hanuram_control;
COMMIT;
-- After migrations and key provisioning, revoke the three temporary operator
-- memberships when no longer needed. Regrant them explicitly before future
-- migrations that need to transfer ownership. Never grant them to application logins.
