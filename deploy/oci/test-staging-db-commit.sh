#!/usr/bin/env bash
set -Eeuo pipefail
# Operator-approved isolated staging persistence rehearsal. No service restart.
cd "$(dirname "$0")/../.."
[[ "${AEPX_STAGING_APPROVED:-}" == yes ]] || { echo "BLOCKED: staging approval required" >&2; exit 3; }
[[ -f .env ]] || { echo "BLOCKED: .env missing" >&2; exit 3; }
COMPOSE=(docker compose --env-file .env -p aepx-oci-staging -f deploy/oci/compose.staging.yml)
cid="$("${COMPOSE[@]}" ps -q postgres)"
[[ -n "$cid" ]] || { echo "BLOCKED: staging postgres unavailable" >&2; exit 3; }
[[ "$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$cid")" == aepx-oci-staging ]] || exit 3
[[ "$(docker inspect -f '{{index .Config.Labels "com.docker.compose.service"}}' "$cid")" == postgres ]] || exit 3
# Durable write and subsequent independent session read, followed by cleanup.
# Does not restart a container, so it is NOT a restart durability test.
probe="aepx_probe_$(date +%s)_$$"
[[ "$probe" =~ ^[a-z0-9_]+$ ]] || exit 3
cleanup() {
  "${COMPOSE[@]}" exec -T postgres psql -X -v ON_ERROR_STOP=1 -U aepx -d aepx -c "DROP TABLE IF EXISTS public.$probe" >/dev/null || true
}
trap cleanup EXIT
"${COMPOSE[@]}" exec -T postgres psql -X -v ON_ERROR_STOP=1 -U aepx -d aepx -c "CREATE TABLE public.$probe (value integer NOT NULL); INSERT INTO public.$probe VALUES (73)"
value="$("${COMPOSE[@]}" exec -T postgres psql -X -At -v ON_ERROR_STOP=1 -U aepx -d aepx -c "SELECT value FROM public.$probe")"
[[ "$value" == 73 ]] || { echo "FAIL: cross-session persistence check" >&2; exit 1; }
echo "PASS: isolated PostgreSQL committed write visible across sessions; no restart tested"
