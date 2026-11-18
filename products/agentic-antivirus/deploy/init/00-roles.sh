#!/bin/sh
# Runs once on first database start: applies the schema and sets the application role's password.
set -eu
for f in /migrations/*.sql; do psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "$f"; done
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "ALTER ROLE aav_app PASSWORD '$AAV_APP_DB_PASSWORD'"
