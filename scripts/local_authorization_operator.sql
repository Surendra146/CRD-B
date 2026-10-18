-- psql entry point for local PostgreSQL 18; use a dedicated local operator.
-- Do not use this wrapper on a production connection.
\set ON_ERROR_STOP on
SET hanuram_setup.expected_database = 'hanuram_dev';
\ir render_authorization_operator.sql
RESET hanuram_setup.expected_database;
