#!/bin/sh
# Runs once on first database start: applies the schema, records each migration as applied (so
# deploy/migrate.sh only applies newer ones) and sets the application role's password.
set -eu
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -q -c \
  "CREATE SCHEMA IF NOT EXISTS aav; CREATE TABLE IF NOT EXISTS aav.schema_migrations (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
for f in /migrations/*.sql; do
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "$f"
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -q -c "INSERT INTO aav.schema_migrations (name) VALUES ('$(basename "$f")')"
done
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "ALTER ROLE aav_app PASSWORD '$AAV_APP_DB_PASSWORD'"
