--
-- PostgreSQL database dump
--

\restrict JSItwpLYgQCyslziLlFxwhFkIOwkTejqZFmEsMyMfhQbFFS6NDalGbEZrAuBkd4

-- Dumped from database version 18.6
-- Dumped by pg_dump version 18.6

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: campaigns; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.campaigns (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    organization_id integer NOT NULL,
    tenant_code character varying(80),
    name character varying(255) NOT NULL,
    description text,
    type character varying(80) NOT NULL,
    trigger jsonb NOT NULL,
    template_id integer,
    audience jsonb NOT NULL,
    schedule jsonb NOT NULL,
    status character varying(80) NOT NULL,
    stats jsonb NOT NULL,
    created_by integer NOT NULL,
    last_run_at timestamp without time zone,
    next_run_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: campaigns_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.campaigns_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: campaigns_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.campaigns_id_seq OWNED BY public.campaigns.id;


--
-- Name: customers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.customers (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    organization_id integer NOT NULL,
    tenant_code character varying(80),
    external_id character varying(255),
    name character varying(255) NOT NULL,
    email character varying(255),
    phone character varying(60),
    whatsapp_number character varying(60),
    address text,
    customer_created_date timestamp without time zone,
    demographics jsonb NOT NULL,
    lifecycle jsonb NOT NULL,
    purchases jsonb NOT NULL,
    interactions jsonb NOT NULL,
    follow_up jsonb NOT NULL,
    preferences jsonb NOT NULL,
    tags jsonb NOT NULL,
    notes text,
    source jsonb NOT NULL,
    module_tags jsonb NOT NULL,
    is_active boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: customers_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.customers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: customers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.customers_id_seq OWNED BY public.customers.id;


--
-- Name: dashboard_configs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dashboard_configs (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    tenant_code character varying(80),
    dashboard_id integer NOT NULL,
    layout jsonb NOT NULL,
    widgets jsonb NOT NULL,
    filters jsonb NOT NULL,
    created_by integer NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: dashboard_configs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.dashboard_configs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: dashboard_configs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.dashboard_configs_id_seq OWNED BY public.dashboard_configs.id;


--
-- Name: dashboards; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dashboards (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    tenant_id integer NOT NULL,
    tenant_code character varying(80),
    created_by integer NOT NULL,
    excel_sources_config jsonb NOT NULL,
    layout jsonb NOT NULL,
    is_active boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: dashboards_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.dashboards_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: dashboards_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.dashboards_id_seq OWNED BY public.dashboards.id;


--
-- Name: data_upload_rows; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.data_upload_rows (
    id integer NOT NULL,
    upload_id integer NOT NULL,
    tenant_id integer NOT NULL,
    organization_id integer NOT NULL,
    row_number integer NOT NULL,
    status character varying(80) NOT NULL,
    raw_data jsonb NOT NULL,
    mapped_data jsonb NOT NULL,
    errors jsonb NOT NULL,
    warnings jsonb NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: data_upload_rows_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.data_upload_rows_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: data_upload_rows_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.data_upload_rows_id_seq OWNED BY public.data_upload_rows.id;


--
-- Name: data_uploads; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.data_uploads (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    organization_id integer NOT NULL,
    tenant_code character varying(80),
    uploaded_by integer NOT NULL,
    file jsonb NOT NULL,
    type character varying(80) NOT NULL,
    column_mapping jsonb NOT NULL,
    status character varying(80) NOT NULL,
    stats jsonb NOT NULL,
    errors jsonb NOT NULL,
    valid_preview jsonb NOT NULL,
    error_preview jsonb NOT NULL,
    saved_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: data_uploads_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.data_uploads_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: data_uploads_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.data_uploads_id_seq OWNED BY public.data_uploads.id;


--
-- Name: generic_json_records; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.generic_json_records (
    id integer NOT NULL,
    model character varying(120) NOT NULL,
    tenant_id integer,
    organization_id integer,
    tenant_code character varying(80),
    payload jsonb NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: generic_json_records_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.generic_json_records_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: generic_json_records_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.generic_json_records_id_seq OWNED BY public.generic_json_records.id;


--
-- Name: gmaps_extracted_leads; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.gmaps_extracted_leads (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    organization_id integer NOT NULL,
    tenant_code character varying(80),
    search_query character varying(255) NOT NULL,
    location character varying(255) NOT NULL,
    business_name character varying(255) NOT NULL,
    phone character varying(80),
    category character varying(120),
    rating character varying(40),
    reviews_count integer NOT NULL,
    address text,
    website character varying(255),
    is_imported boolean NOT NULL,
    customer_id integer,
    raw_data jsonb NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: gmaps_extracted_leads_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.gmaps_extracted_leads_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: gmaps_extracted_leads_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.gmaps_extracted_leads_id_seq OWNED BY public.gmaps_extracted_leads.id;


--
-- Name: organizations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.organizations (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    slug character varying(255),
    owner_id integer,
    tenant_id integer,
    tenant_code character varying(80),
    members jsonb NOT NULL,
    custom_roles jsonb NOT NULL,
    settings jsonb NOT NULL,
    branding jsonb NOT NULL,
    limits jsonb NOT NULL,
    usage jsonb NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: organizations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.organizations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: organizations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.organizations_id_seq OWNED BY public.organizations.id;


--
-- Name: segments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.segments (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    organization_id integer NOT NULL,
    tenant_code character varying(80),
    code character varying(255) NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    filters jsonb NOT NULL,
    is_active boolean NOT NULL,
    created_by integer,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: segments_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.segments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: segments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.segments_id_seq OWNED BY public.segments.id;


--
-- Name: tenants; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tenants (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    subdomain character varying(255),
    code character varying(80),
    is_active boolean NOT NULL,
    settings jsonb NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: tenants_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tenants_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tenants_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tenants_id_seq OWNED BY public.tenants.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id integer NOT NULL,
    email character varying(255) NOT NULL,
    password character varying(255) NOT NULL,
    name character varying(255) NOT NULL,
    phone character varying(60),
    phone_verified boolean NOT NULL,
    phone_otp_hash character varying(255),
    phone_otp_expires_at timestamp without time zone,
    company jsonb NOT NULL,
    role character varying(80) NOT NULL,
    role_profile_name character varying(255),
    allowed_modules jsonb NOT NULL,
    organization_id integer,
    tenant_id integer,
    tenant_code character varying(80),
    subscription jsonb NOT NULL,
    settings jsonb NOT NULL,
    is_active boolean NOT NULL,
    last_login timestamp without time zone,
    password_changed_at timestamp without time zone,
    password_reset_token character varying(255),
    password_reset_expires timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: whatsapp_auto_responders; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.whatsapp_auto_responders (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    organization_id integer NOT NULL,
    tenant_code character varying(80),
    name character varying(255) NOT NULL,
    trigger_type character varying(80) NOT NULL,
    keywords jsonb NOT NULL,
    response_message text NOT NULL,
    buttons jsonb NOT NULL,
    media_files jsonb NOT NULL,
    is_active boolean NOT NULL,
    priority integer NOT NULL,
    match_count integer NOT NULL,
    last_triggered_at timestamp without time zone,
    created_by integer,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: whatsapp_auto_responders_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.whatsapp_auto_responders_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: whatsapp_auto_responders_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.whatsapp_auto_responders_id_seq OWNED BY public.whatsapp_auto_responders.id;


--
-- Name: whatsapp_bulk_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.whatsapp_bulk_jobs (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    organization_id integer NOT NULL,
    tenant_code character varying(80),
    title character varying(255) NOT NULL,
    audience_type character varying(80) NOT NULL,
    audience_payload jsonb NOT NULL,
    message_template text NOT NULL,
    buttons jsonb NOT NULL,
    media_files jsonb NOT NULL,
    batch_delay_seconds integer NOT NULL,
    scheduled_at timestamp without time zone,
    status character varying(80) NOT NULL,
    stats jsonb NOT NULL,
    recipients_summary jsonb NOT NULL,
    created_by integer,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: whatsapp_bulk_jobs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.whatsapp_bulk_jobs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: whatsapp_bulk_jobs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.whatsapp_bulk_jobs_id_seq OWNED BY public.whatsapp_bulk_jobs.id;


--
-- Name: whatsapp_connections; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.whatsapp_connections (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    organization_id integer NOT NULL,
    waba_id character varying(80) NOT NULL,
    phone_number_id character varying(80) NOT NULL,
    display_phone_number character varying(80),
    verified_name character varying(255),
    encrypted_access_token text NOT NULL,
    connected_by integer NOT NULL,
    token_expires_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: whatsapp_connections_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.whatsapp_connections_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: whatsapp_connections_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.whatsapp_connections_id_seq OWNED BY public.whatsapp_connections.id;


--
-- Name: whatsapp_group_tasks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.whatsapp_group_tasks (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    organization_id integer NOT NULL,
    tenant_code character varying(80),
    task_type character varying(80) NOT NULL,
    title character varying(255) NOT NULL,
    group_name character varying(255),
    extracted_count integer NOT NULL,
    status character varying(80) NOT NULL,
    details jsonb NOT NULL,
    created_by integer,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: whatsapp_group_tasks_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.whatsapp_group_tasks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: whatsapp_group_tasks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.whatsapp_group_tasks_id_seq OWNED BY public.whatsapp_group_tasks.id;


--
-- Name: whatsapp_signup_attempts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.whatsapp_signup_attempts (
    id character varying(80) NOT NULL,
    tenant_id integer NOT NULL,
    organization_id integer NOT NULL,
    user_id integer NOT NULL,
    expires_at timestamp without time zone NOT NULL,
    encrypted_access_token text,
    token_expires_at timestamp without time zone,
    phase character varying(30) NOT NULL
);


--
-- Name: whatsapp_templates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.whatsapp_templates (
    id integer NOT NULL,
    tenant_id integer NOT NULL,
    organization_id integer NOT NULL,
    tenant_code character varying(80),
    name character varying(255) NOT NULL,
    category character varying(80) NOT NULL,
    whatsapp_template_name character varying(255),
    content jsonb NOT NULL,
    variables jsonb NOT NULL,
    targeting jsonb NOT NULL,
    stats jsonb NOT NULL,
    is_active boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: whatsapp_templates_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.whatsapp_templates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: whatsapp_templates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.whatsapp_templates_id_seq OWNED BY public.whatsapp_templates.id;


--
-- Name: campaigns id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaigns ALTER COLUMN id SET DEFAULT nextval('public.campaigns_id_seq'::regclass);


--
-- Name: customers id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customers ALTER COLUMN id SET DEFAULT nextval('public.customers_id_seq'::regclass);


--
-- Name: dashboard_configs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dashboard_configs ALTER COLUMN id SET DEFAULT nextval('public.dashboard_configs_id_seq'::regclass);


--
-- Name: dashboards id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dashboards ALTER COLUMN id SET DEFAULT nextval('public.dashboards_id_seq'::regclass);


--
-- Name: data_upload_rows id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_upload_rows ALTER COLUMN id SET DEFAULT nextval('public.data_upload_rows_id_seq'::regclass);


--
-- Name: data_uploads id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_uploads ALTER COLUMN id SET DEFAULT nextval('public.data_uploads_id_seq'::regclass);


--
-- Name: generic_json_records id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.generic_json_records ALTER COLUMN id SET DEFAULT nextval('public.generic_json_records_id_seq'::regclass);


--
-- Name: gmaps_extracted_leads id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gmaps_extracted_leads ALTER COLUMN id SET DEFAULT nextval('public.gmaps_extracted_leads_id_seq'::regclass);


--
-- Name: organizations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organizations ALTER COLUMN id SET DEFAULT nextval('public.organizations_id_seq'::regclass);


--
-- Name: segments id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.segments ALTER COLUMN id SET DEFAULT nextval('public.segments_id_seq'::regclass);


--
-- Name: tenants id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenants ALTER COLUMN id SET DEFAULT nextval('public.tenants_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: whatsapp_auto_responders id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.whatsapp_auto_responders ALTER COLUMN id SET DEFAULT nextval('public.whatsapp_auto_responders_id_seq'::regclass);


--
-- Name: whatsapp_bulk_jobs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.whatsapp_bulk_jobs ALTER COLUMN id SET DEFAULT nextval('public.whatsapp_bulk_jobs_id_seq'::regclass);


--
-- Name: whatsapp_connections id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.whatsapp_connections ALTER COLUMN id SET DEFAULT nextval('public.whatsapp_connections_id_seq'::regclass);


--
-- Name: whatsapp_group_tasks id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.whatsapp_group_tasks ALTER COLUMN id SET DEFAULT nextval('public.whatsapp_group_tasks_id_seq'::regclass);


--
-- Name: whatsapp_templates id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.whatsapp_templates ALTER COLUMN id SET DEFAULT nextval('public.whatsapp_templates_id_seq'::regclass);


--
-- Name: campaigns campaigns_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaigns
    ADD CONSTRAINT campaigns_pkey PRIMARY KEY (id);


--
-- Name: customers customers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT customers_pkey PRIMARY KEY (id);


--
-- Name: dashboard_configs dashboard_configs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dashboard_configs
    ADD CONSTRAINT dashboard_configs_pkey PRIMARY KEY (id);


--
-- Name: dashboards dashboards_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dashboards
    ADD CONSTRAINT dashboards_pkey PRIMARY KEY (id);


--
-- Name: data_upload_rows data_upload_rows_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_upload_rows
    ADD CONSTRAINT data_upload_rows_pkey PRIMARY KEY (id);


--
-- Name: data_uploads data_uploads_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_uploads
    ADD CONSTRAINT data_uploads_pkey PRIMARY KEY (id);


--
-- Name: generic_json_records generic_json_records_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.generic_json_records
    ADD CONSTRAINT generic_json_records_pkey PRIMARY KEY (id);


--
-- Name: gmaps_extracted_leads gmaps_extracted_leads_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gmaps_extracted_leads
    ADD CONSTRAINT gmaps_extracted_leads_pkey PRIMARY KEY (id);


--
-- Name: organizations organizations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT organizations_pkey PRIMARY KEY (id);


--
-- Name: organizations organizations_slug_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT organizations_slug_key UNIQUE (slug);


--
-- Name: segments segments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.segments
    ADD CONSTRAINT segments_pkey PRIMARY KEY (id);


--
-- Name: segments segments_tenant_id_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.segments
    ADD CONSTRAINT segments_tenant_id_code_key UNIQUE (tenant_id, code);


--
-- Name: segments segments_tenant_id_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.segments
    ADD CONSTRAINT segments_tenant_id_name_key UNIQUE (tenant_id, name);


--
-- Name: tenants tenants_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT tenants_pkey PRIMARY KEY (id);


--
-- Name: tenants tenants_subdomain_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT tenants_subdomain_key UNIQUE (subdomain);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: whatsapp_auto_responders whatsapp_auto_responders_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.whatsapp_auto_responders
    ADD CONSTRAINT whatsapp_auto_responders_pkey PRIMARY KEY (id);


--
-- Name: whatsapp_bulk_jobs whatsapp_bulk_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.whatsapp_bulk_jobs
    ADD CONSTRAINT whatsapp_bulk_jobs_pkey PRIMARY KEY (id);


--
-- Name: whatsapp_connections whatsapp_connections_organization_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.whatsapp_connections
    ADD CONSTRAINT whatsapp_connections_organization_id_key UNIQUE (organization_id);


--
-- Name: whatsapp_connections whatsapp_connections_phone_number_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.whatsapp_connections
    ADD CONSTRAINT whatsapp_connections_phone_number_id_key UNIQUE (phone_number_id);


--
-- Name: whatsapp_connections whatsapp_connections_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.whatsapp_connections
    ADD CONSTRAINT whatsapp_connections_pkey PRIMARY KEY (id);


--
-- Name: whatsapp_group_tasks whatsapp_group_tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.whatsapp_group_tasks
    ADD CONSTRAINT whatsapp_group_tasks_pkey PRIMARY KEY (id);


--
-- Name: whatsapp_signup_attempts whatsapp_signup_attempts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.whatsapp_signup_attempts
    ADD CONSTRAINT whatsapp_signup_attempts_pkey PRIMARY KEY (id);


--
-- Name: whatsapp_templates whatsapp_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.whatsapp_templates
    ADD CONSTRAINT whatsapp_templates_pkey PRIMARY KEY (id);


--
-- Name: ix_campaigns_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_campaigns_organization_id ON public.campaigns USING btree (organization_id);


--
-- Name: ix_campaigns_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_campaigns_status ON public.campaigns USING btree (status);


--
-- Name: ix_campaigns_template_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_campaigns_template_id ON public.campaigns USING btree (template_id);


--
-- Name: ix_campaigns_tenant_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_campaigns_tenant_code ON public.campaigns USING btree (tenant_code);


--
-- Name: ix_campaigns_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_campaigns_tenant_id ON public.campaigns USING btree (tenant_id);


--
-- Name: ix_campaigns_tenant_org; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_campaigns_tenant_org ON public.campaigns USING btree (tenant_id, organization_id);


--
-- Name: ix_customers_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_customers_email ON public.customers USING btree (email);


--
-- Name: ix_customers_external_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_customers_external_id ON public.customers USING btree (external_id);


--
-- Name: ix_customers_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_customers_organization_id ON public.customers USING btree (organization_id);


--
-- Name: ix_customers_phone; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_customers_phone ON public.customers USING btree (phone);


--
-- Name: ix_customers_tenant_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_customers_tenant_code ON public.customers USING btree (tenant_code);


--
-- Name: ix_customers_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_customers_tenant_id ON public.customers USING btree (tenant_id);


--
-- Name: ix_customers_tenant_org; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_customers_tenant_org ON public.customers USING btree (tenant_id, organization_id);


--
-- Name: ix_customers_tenant_phone; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_customers_tenant_phone ON public.customers USING btree (tenant_id, phone);


--
-- Name: ix_dashboard_configs_dashboard_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dashboard_configs_dashboard_id ON public.dashboard_configs USING btree (dashboard_id);


--
-- Name: ix_dashboard_configs_tenant_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dashboard_configs_tenant_code ON public.dashboard_configs USING btree (tenant_code);


--
-- Name: ix_dashboard_configs_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dashboard_configs_tenant_id ON public.dashboard_configs USING btree (tenant_id);


--
-- Name: ix_dashboards_tenant_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dashboards_tenant_active ON public.dashboards USING btree (tenant_id, is_active);


--
-- Name: ix_dashboards_tenant_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dashboards_tenant_code ON public.dashboards USING btree (tenant_code);


--
-- Name: ix_dashboards_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dashboards_tenant_id ON public.dashboards USING btree (tenant_id);


--
-- Name: ix_data_upload_rows_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_data_upload_rows_organization_id ON public.data_upload_rows USING btree (organization_id);


--
-- Name: ix_data_upload_rows_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_data_upload_rows_status ON public.data_upload_rows USING btree (status);


--
-- Name: ix_data_upload_rows_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_data_upload_rows_tenant_id ON public.data_upload_rows USING btree (tenant_id);


--
-- Name: ix_data_upload_rows_tenant_upload; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_data_upload_rows_tenant_upload ON public.data_upload_rows USING btree (tenant_id, upload_id);


--
-- Name: ix_data_upload_rows_upload_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_data_upload_rows_upload_id ON public.data_upload_rows USING btree (upload_id);


--
-- Name: ix_data_upload_rows_upload_row; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_data_upload_rows_upload_row ON public.data_upload_rows USING btree (upload_id, row_number);


--
-- Name: ix_data_upload_rows_upload_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_data_upload_rows_upload_status ON public.data_upload_rows USING btree (upload_id, status);


--
-- Name: ix_data_uploads_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_data_uploads_organization_id ON public.data_uploads USING btree (organization_id);


--
-- Name: ix_data_uploads_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_data_uploads_status ON public.data_uploads USING btree (status);


--
-- Name: ix_data_uploads_tenant_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_data_uploads_tenant_code ON public.data_uploads USING btree (tenant_code);


--
-- Name: ix_data_uploads_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_data_uploads_tenant_id ON public.data_uploads USING btree (tenant_id);


--
-- Name: ix_data_uploads_tenant_org_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_data_uploads_tenant_org_status ON public.data_uploads USING btree (tenant_id, organization_id, status);


--
-- Name: ix_generic_json_records_model; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_generic_json_records_model ON public.generic_json_records USING btree (model);


--
-- Name: ix_generic_json_records_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_generic_json_records_organization_id ON public.generic_json_records USING btree (organization_id);


--
-- Name: ix_generic_json_records_tenant_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_generic_json_records_tenant_code ON public.generic_json_records USING btree (tenant_code);


--
-- Name: ix_generic_json_records_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_generic_json_records_tenant_id ON public.generic_json_records USING btree (tenant_id);


--
-- Name: ix_gmaps_extracted_leads_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_gmaps_extracted_leads_organization_id ON public.gmaps_extracted_leads USING btree (organization_id);


--
-- Name: ix_gmaps_extracted_leads_phone; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_gmaps_extracted_leads_phone ON public.gmaps_extracted_leads USING btree (phone);


--
-- Name: ix_gmaps_extracted_leads_search_query; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_gmaps_extracted_leads_search_query ON public.gmaps_extracted_leads USING btree (search_query);


--
-- Name: ix_gmaps_extracted_leads_tenant_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_gmaps_extracted_leads_tenant_code ON public.gmaps_extracted_leads USING btree (tenant_code);


--
-- Name: ix_gmaps_extracted_leads_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_gmaps_extracted_leads_tenant_id ON public.gmaps_extracted_leads USING btree (tenant_id);


--
-- Name: ix_gmaps_leads_tenant_org; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_gmaps_leads_tenant_org ON public.gmaps_extracted_leads USING btree (tenant_id, organization_id);


--
-- Name: ix_organizations_tenant_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_organizations_tenant_code ON public.organizations USING btree (tenant_code);


--
-- Name: ix_organizations_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_organizations_tenant_id ON public.organizations USING btree (tenant_id);


--
-- Name: ix_segments_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_segments_organization_id ON public.segments USING btree (organization_id);


--
-- Name: ix_segments_tenant_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_segments_tenant_code ON public.segments USING btree (tenant_code);


--
-- Name: ix_segments_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_segments_tenant_id ON public.segments USING btree (tenant_id);


--
-- Name: ix_segments_tenant_org; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_segments_tenant_org ON public.segments USING btree (tenant_id, organization_id);


--
-- Name: ix_tenants_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_tenants_code ON public.tenants USING btree (code);


--
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);


--
-- Name: ix_users_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_users_organization_id ON public.users USING btree (organization_id);


--
-- Name: ix_users_tenant_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_users_tenant_code ON public.users USING btree (tenant_code);


--
-- Name: ix_users_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_users_tenant_id ON public.users USING btree (tenant_id);


--
-- Name: ix_whatsapp_auto_responders_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_whatsapp_auto_responders_organization_id ON public.whatsapp_auto_responders USING btree (organization_id);


--
-- Name: ix_whatsapp_auto_responders_tenant_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_whatsapp_auto_responders_tenant_code ON public.whatsapp_auto_responders USING btree (tenant_code);


--
-- Name: ix_whatsapp_auto_responders_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_whatsapp_auto_responders_tenant_id ON public.whatsapp_auto_responders USING btree (tenant_id);


--
-- Name: ix_whatsapp_auto_responders_tenant_org; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_whatsapp_auto_responders_tenant_org ON public.whatsapp_auto_responders USING btree (tenant_id, organization_id);


--
-- Name: ix_whatsapp_bulk_jobs_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_whatsapp_bulk_jobs_organization_id ON public.whatsapp_bulk_jobs USING btree (organization_id);


--
-- Name: ix_whatsapp_bulk_jobs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_whatsapp_bulk_jobs_status ON public.whatsapp_bulk_jobs USING btree (status);


--
-- Name: ix_whatsapp_bulk_jobs_tenant_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_whatsapp_bulk_jobs_tenant_code ON public.whatsapp_bulk_jobs USING btree (tenant_code);


--
-- Name: ix_whatsapp_bulk_jobs_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_whatsapp_bulk_jobs_tenant_id ON public.whatsapp_bulk_jobs USING btree (tenant_id);


--
-- Name: ix_whatsapp_bulk_jobs_tenant_org; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_whatsapp_bulk_jobs_tenant_org ON public.whatsapp_bulk_jobs USING btree (tenant_id, organization_id);


--
-- Name: ix_whatsapp_connections_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_whatsapp_connections_tenant_id ON public.whatsapp_connections USING btree (tenant_id);


--
-- Name: ix_whatsapp_group_tasks_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_whatsapp_group_tasks_organization_id ON public.whatsapp_group_tasks USING btree (organization_id);


--
-- Name: ix_whatsapp_group_tasks_tenant_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_whatsapp_group_tasks_tenant_code ON public.whatsapp_group_tasks USING btree (tenant_code);


--
-- Name: ix_whatsapp_group_tasks_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_whatsapp_group_tasks_tenant_id ON public.whatsapp_group_tasks USING btree (tenant_id);


--
-- Name: ix_whatsapp_group_tasks_tenant_org; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_whatsapp_group_tasks_tenant_org ON public.whatsapp_group_tasks USING btree (tenant_id, organization_id);


--
-- Name: ix_whatsapp_templates_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_whatsapp_templates_organization_id ON public.whatsapp_templates USING btree (organization_id);


--
-- Name: ix_whatsapp_templates_tenant_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_whatsapp_templates_tenant_code ON public.whatsapp_templates USING btree (tenant_code);


--
-- Name: ix_whatsapp_templates_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_whatsapp_templates_tenant_id ON public.whatsapp_templates USING btree (tenant_id);


--
-- Name: ix_whatsapp_templates_tenant_org; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_whatsapp_templates_tenant_org ON public.whatsapp_templates USING btree (tenant_id, organization_id);


--
-- Name: campaigns campaigns_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaigns
    ADD CONSTRAINT campaigns_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: campaigns campaigns_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaigns
    ADD CONSTRAINT campaigns_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: campaigns campaigns_template_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaigns
    ADD CONSTRAINT campaigns_template_id_fkey FOREIGN KEY (template_id) REFERENCES public.whatsapp_templates(id);


--
-- Name: campaigns campaigns_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaigns
    ADD CONSTRAINT campaigns_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: customers customers_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT customers_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: customers customers_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT customers_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: dashboard_configs dashboard_configs_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dashboard_configs
    ADD CONSTRAINT dashboard_configs_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: dashboard_configs dashboard_configs_dashboard_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dashboard_configs
    ADD CONSTRAINT dashboard_configs_dashboard_id_fkey FOREIGN KEY (dashboard_id) REFERENCES public.dashboards(id);


--
-- Name: dashboard_configs dashboard_configs_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dashboard_configs
    ADD CONSTRAINT dashboard_configs_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: dashboards dashboards_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dashboards
    ADD CONSTRAINT dashboards_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: dashboards dashboards_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dashboards
    ADD CONSTRAINT dashboards_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: data_upload_rows data_upload_rows_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_upload_rows
    ADD CONSTRAINT data_upload_rows_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: data_upload_rows data_upload_rows_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_upload_rows
    ADD CONSTRAINT data_upload_rows_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: data_upload_rows data_upload_rows_upload_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_upload_rows
    ADD CONSTRAINT data_upload_rows_upload_id_fkey FOREIGN KEY (upload_id) REFERENCES public.data_uploads(id);


--
-- Name: data_uploads data_uploads_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_uploads
    ADD CONSTRAINT data_uploads_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: data_uploads data_uploads_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_uploads
    ADD CONSTRAINT data_uploads_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: data_uploads data_uploads_uploaded_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_uploads
    ADD CONSTRAINT data_uploads_uploaded_by_fkey FOREIGN KEY (uploaded_by) REFERENCES public.users(id);


--
-- Name: generic_json_records generic_json_records_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.generic_json_records
    ADD CONSTRAINT generic_json_records_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: gmaps_extracted_leads gmaps_extracted_leads_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gmaps_extracted_leads
    ADD CONSTRAINT gmaps_extracted_leads_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id);


--
-- Name: gmaps_extracted_leads gmaps_extracted_leads_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gmaps_extracted_leads
    ADD CONSTRAINT gmaps_extracted_leads_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: gmaps_extracted_leads gmaps_extracted_leads_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gmaps_extracted_leads
    ADD CONSTRAINT gmaps_extracted_leads_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: organizations organizations_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT organizations_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: segments segments_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.segments
    ADD CONSTRAINT segments_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: segments segments_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.segments
    ADD CONSTRAINT segments_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: segments segments_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.segments
    ADD CONSTRAINT segments_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: users users_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: users users_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: whatsapp_auto_responders whatsapp_auto_responders_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.whatsapp_auto_responders
    ADD CONSTRAINT whatsapp_auto_responders_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: whatsapp_auto_responders whatsapp_auto_responders_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.whatsapp_auto_responders
    ADD CONSTRAINT whatsapp_auto_responders_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: whatsapp_auto_responders whatsapp_auto_responders_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.whatsapp_auto_responders
    ADD CONSTRAINT whatsapp_auto_responders_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: whatsapp_bulk_jobs whatsapp_bulk_jobs_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.whatsapp_bulk_jobs
    ADD CONSTRAINT whatsapp_bulk_jobs_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: whatsapp_bulk_jobs whatsapp_bulk_jobs_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.whatsapp_bulk_jobs
    ADD CONSTRAINT whatsapp_bulk_jobs_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: whatsapp_bulk_jobs whatsapp_bulk_jobs_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.whatsapp_bulk_jobs
    ADD CONSTRAINT whatsapp_bulk_jobs_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: whatsapp_connections whatsapp_connections_connected_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.whatsapp_connections
    ADD CONSTRAINT whatsapp_connections_connected_by_fkey FOREIGN KEY (connected_by) REFERENCES public.users(id);


--
-- Name: whatsapp_connections whatsapp_connections_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.whatsapp_connections
    ADD CONSTRAINT whatsapp_connections_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: whatsapp_connections whatsapp_connections_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.whatsapp_connections
    ADD CONSTRAINT whatsapp_connections_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: whatsapp_group_tasks whatsapp_group_tasks_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.whatsapp_group_tasks
    ADD CONSTRAINT whatsapp_group_tasks_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: whatsapp_group_tasks whatsapp_group_tasks_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.whatsapp_group_tasks
    ADD CONSTRAINT whatsapp_group_tasks_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: whatsapp_group_tasks whatsapp_group_tasks_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.whatsapp_group_tasks
    ADD CONSTRAINT whatsapp_group_tasks_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: whatsapp_signup_attempts whatsapp_signup_attempts_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.whatsapp_signup_attempts
    ADD CONSTRAINT whatsapp_signup_attempts_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: whatsapp_signup_attempts whatsapp_signup_attempts_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.whatsapp_signup_attempts
    ADD CONSTRAINT whatsapp_signup_attempts_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: whatsapp_signup_attempts whatsapp_signup_attempts_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.whatsapp_signup_attempts
    ADD CONSTRAINT whatsapp_signup_attempts_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: whatsapp_templates whatsapp_templates_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.whatsapp_templates
    ADD CONSTRAINT whatsapp_templates_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: whatsapp_templates whatsapp_templates_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.whatsapp_templates
    ADD CONSTRAINT whatsapp_templates_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- PostgreSQL database dump complete
--

\unrestrict JSItwpLYgQCyslziLlFxwhFkIOwkTejqZFmEsMyMfhQbFFS6NDalGbEZrAuBkd4

