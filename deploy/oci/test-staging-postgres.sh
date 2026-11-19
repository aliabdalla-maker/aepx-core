#!/usr/bin/env bash
set -Eeuo pipefail
# Explicit operator-invoked, isolated staging-only PostgreSQL R/W acceptance.
# A transaction-scoped temporary table is rolled back; no persistent data changes.
cd "$(dirname "$0")/../.."
[[ "${AEPX_STAGING_APPROVED:-}" == "yes" ]] || {
  echo "BLOCKED: isolated staging operator approval required" >&2; exit 3;
}
[[ -f .env ]] || { echo "BLOCKED: private .env missing" >&2; exit 3; }
COMPOSE=(docker compose --env-file .env -p aepx-oci-staging -f deploy/oci/compose.staging.yml)
cid="$("${COMPOSE[@]}" ps -q postgres)"
[[ -n "$cid" ]] || { echo "BLOCKED: isolated staging postgres not running" >&2; exit 3; }
# Assert the container belongs to the dedicated project; never touch production.
project="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$cid")"
service="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.service"}}' "$cid")"
[[ "$project" == "aepx-oci-staging" && "$service" == "postgres" ]] || {
  echo "BLOCKED: container identity mismatch" >&2; exit 3;
}
"${COMPOSE[@]}" exec -T postgres psql -X -v ON_ERROR_STOP=1 -U aepx -d aepx <<'SQL'
BEGIN;
CREATE TEMP TABLE aepx_acceptance_probe (id integer PRIMARY KEY, note text NOT NULL) ON COMMIT DROP;
INSERT INTO aepx_acceptance_probe VALUES (1, 'staging-read-write');
DO $$
BEGIN
 IF (SELECT note FROM aepx_acceptance_probe WHERE id=1) <> 'staging-read-write' THEN
  RAISE EXCEPTION 'staging read/write probe failed';
 END IF;
END
$$;
ROLLBACK;
SQL
echo "PASS: isolated staging PostgreSQL read/write transaction rolled back"
