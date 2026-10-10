-- Run as a database administrator AFTER the migration and restore rehearsal.
-- Supply login passwords through your secret manager, never commit them here.
-- Managed PostgreSQL providers may require their support to grant BYPASSRLS.
CREATE ROLE hanuram_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
CREATE ROLE hanuram_control NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE BYPASSRLS;
GRANT USAGE ON SCHEMA public TO hanuram_runtime, hanuram_control;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO hanuram_control;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO hanuram_control;
DO $$
DECLARE record record;
BEGIN
  FOR record IN SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='public' AND c.relkind='r' AND c.relrowsecurity AND c.relforcerowsecurity
  LOOP
    IF record.relname IN ('audit_events', 'consent_events') THEN
      EXECUTE format('GRANT SELECT, INSERT ON TABLE public.%I TO hanuram_runtime', record.relname);
    ELSIF record.relname IN ('usage_entries', 'tenants', 'users', 'saas_invoices', 'subscriptions') THEN
      EXECUTE format('GRANT SELECT ON TABLE public.%I TO hanuram_runtime', record.relname);
    ELSE
      EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.%I TO hanuram_runtime', record.relname);
    END IF;
  END LOOP;
END $$;
-- Only the staff control connection may mutate subscriptions.
REVOKE INSERT, UPDATE, DELETE ON subscriptions FROM hanuram_runtime;
GRANT SELECT ON subscriptions TO hanuram_runtime;
GRANT SELECT ON subscription_plans TO hanuram_runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO hanuram_runtime;
-- Create distinct login roles, grant these groups, and revoke PUBLIC privileges.
-- Runtime must never inherit owner, control, CREATE, TRUNCATE or BYPASSRLS rights.
-- Reapply reviewed grants for each later migration; do not grant ALL TABLES to runtime.
