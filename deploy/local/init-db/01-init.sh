#!/bin/bash
# Runs ONCE, on first initialization of an empty pgvector data volume (the
# pgvector image executes everything in /docker-entrypoint-initdb.d as postgres).
# Creates the extensions and the app roles the restored dump + API expect.
set -e

psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<SQL
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

DO \$\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'posterbot_owner') THEN
    CREATE ROLE posterbot_owner LOGIN PASSWORD '${POSTERBOT_OWNER_PASSWORD}';
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'posterbot_ro') THEN
    CREATE ROLE posterbot_ro LOGIN PASSWORD '${POSTERBOT_RO_PASSWORD}';
  END IF;
END \$\$;

ALTER ROLE posterbot_ro SET default_transaction_read_only = on;
ALTER ROLE posterbot_ro SET statement_timeout = '5s';
ALTER ROLE posterbot_ro SET work_mem = '64MB';
GRANT USAGE ON SCHEMA public TO posterbot_ro;
SQL

echo "posterbot: extensions + roles created. Load data with scripts/restore.sh."
