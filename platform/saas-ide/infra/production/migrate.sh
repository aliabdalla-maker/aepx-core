#!/bin/sh
# Applies the IDE schema to the production database. Safe to run on every deploy:
# each migration file is recorded in aepx_schema_migrations and applied only once.
# Passwords are read from files written by the ide-secrets service; nothing is logged.
set -eu
SECRETS=${SECRETS_DIR:-/run/ide-secrets}
export PGHOST=${PGHOST:-ide-db} PGUSER=postgres PGDATABASE=ide
export PGPASSWORD="$(cat "$SECRETS/postgres")"
RUNTIME_PW="$(cat "$SECRETS/ide_runtime")"
KEYCLOAK_PW="$(cat "$SECRETS/keycloak_db")"
psql_q() { psql -v ON_ERROR_STOP=1 -q -X "$@"; }

until pg_isready -q; do echo "waiting for database"; sleep 2; done

# Roles: runtime role without superuser or RLS bypass; Keycloak gets its own database.
psql_q -v rpw="$RUNTIME_PW" -v kpw="$KEYCLOAK_PW" <<'SQL'
SELECT format('CREATE ROLE ide_runtime LOGIN PASSWORD %L NOSUPERUSER NOBYPASSRLS', :'rpw')
  WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ide_runtime') \gexec
SELECT format('ALTER ROLE ide_runtime PASSWORD %L', :'rpw') \gexec
SELECT format('CREATE ROLE keycloak LOGIN PASSWORD %L NOSUPERUSER NOBYPASSRLS', :'kpw')
  WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'keycloak') \gexec
SELECT format('ALTER ROLE keycloak PASSWORD %L', :'kpw') \gexec
SELECT 'CREATE DATABASE keycloak OWNER keycloak'
  WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'keycloak') \gexec
CREATE TABLE IF NOT EXISTS aepx_schema_migrations (
  name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now());
SQL

for f in /migrations/*.sql; do
  name=$(basename "$f")
  done_already=$(psql_q -tA -v n="$name" <<'SQL'
SELECT 1 FROM aepx_schema_migrations WHERE name = :'n';
SQL
)
  if [ "$done_already" = "1" ]; then continue; fi
  echo "applying $name"
  { cat "$f"; printf "\nINSERT INTO aepx_schema_migrations(name) VALUES ('%s');\n" "$name"; } \
    | psql_q --single-transaction
done

# Least-privilege grants for the API (same set the CI integration tests use).
psql_q <<'SQL'
GRANT USAGE ON SCHEMA public TO ide_runtime;
GRANT SELECT ON ide_memberships TO ide_runtime;
GRANT SELECT, INSERT, UPDATE ON ide_projects, ide_workspace_files, ide_agent_runs TO ide_runtime;
GRANT SELECT, INSERT ON ide_knowledge_documents, ide_agent_audit TO ide_runtime;
GRANT SELECT, INSERT, DELETE ON ide_knowledge_vectors TO ide_runtime;
GRANT SELECT, INSERT, UPDATE ON ide_agent_jobs, ide_tool_approvals, ide_agent_spend TO ide_runtime;
GRANT SELECT, UPDATE ON ide_agent_budgets TO ide_runtime;
GRANT SELECT, INSERT ON ide_agent_reconciliation, ide_billing_events TO ide_runtime;
GRANT SELECT, INSERT, UPDATE ON ide_mcp_executions, ide_entitlements TO ide_runtime;
GRANT SELECT, INSERT, UPDATE ON ide_media_jobs, ide_media_assets, ide_social_posts TO ide_runtime;
GRANT SELECT, INSERT ON ide_media_audit TO ide_runtime;
GRANT EXECUTE ON FUNCTION ide_open_personal_workspace(VARCHAR, VARCHAR) TO ide_runtime;
GRANT SELECT, INSERT, UPDATE ON ide_ai_monthly_spend, ide_ai_usage TO ide_runtime;
GRANT EXECUTE ON FUNCTION ide_dispatchable_tenants(INTEGER), ide_ensure_agent_budget(VARCHAR, BIGINT) TO ide_runtime;
SQL
echo "IDE database ready"
