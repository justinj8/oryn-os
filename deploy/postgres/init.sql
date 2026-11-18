-- Runs once when the Postgres volume is first created.
-- Two roles: oryn_owner (migrations/seed, BYPASSRLS) and oryn_app (runtime, subject to RLS).
CREATE ROLE oryn_owner LOGIN PASSWORD 'oryn_owner' BYPASSRLS CREATEDB;
CREATE ROLE oryn_app LOGIN PASSWORD 'oryn_app' NOBYPASSRLS;
CREATE ROLE temporal LOGIN PASSWORD 'temporal' CREATEDB;

CREATE DATABASE oryn OWNER oryn_owner;
CREATE DATABASE oryn_test OWNER oryn_owner;
CREATE DATABASE temporal OWNER temporal;
CREATE DATABASE temporal_visibility OWNER temporal;

\connect oryn
CREATE EXTENSION IF NOT EXISTS vector;
GRANT CONNECT ON DATABASE oryn TO oryn_app;
\connect oryn_test
CREATE EXTENSION IF NOT EXISTS vector;
GRANT CONNECT ON DATABASE oryn_test TO oryn_app;
