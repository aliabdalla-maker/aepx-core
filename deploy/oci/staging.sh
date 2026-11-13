#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/../.."
COMPOSE=(docker compose --env-file .env -p aepx-oci-staging -f deploy/oci/compose.staging.yml)
case "${1:---validate}" in
  --validate)
    python3 deploy/oci/check-staging-policy.py
    python3 deploy/oci/validate-secrets.py
    "${COMPOSE[@]}" config --quiet
    python3 - <<'PY'
import json,subprocess
cfg=json.loads(subprocess.check_output(["docker","compose","--env-file",".env","-p","aepx-oci-staging","-f","deploy/oci/compose.staging.yml","config","--format","json"],text=True))
for name,svc in cfg["services"].items():
    assert not svc.get("ports"),f"Public port prohibited: {name}"
    assert not svc.get("privileged"),f"Privileged service prohibited: {name}"
    assert svc.get("network_mode")!="host",f"Host network prohibited: {name}"
print("PASS: private staging configuration")
PY
    ;;
  --status)
    "${COMPOSE[@]}" ps
    ;;
  --logs)
    "${COMPOSE[@]}" logs --tail=100 --no-color
    ;;
  --stop)
    [[ "${AEPX_STAGING_APPROVED:-}" == "yes" ]] || { echo "BLOCKED: explicit staging operator approval required" >&2; exit 3; }
    "${COMPOSE[@]}" stop
    ;;
  --db-commit)
    bash deploy/oci/test-staging-db-commit.sh
    ;;
  --db-smoke)
    bash deploy/oci/test-staging-postgres.sh
    ;;
  --smoke)
    "${COMPOSE[@]}" ps --status running
    "${COMPOSE[@]}" exec -T postgres pg_isready -U aepx -d aepx
    redis_reply="$("${COMPOSE[@]}" exec -T redis redis-cli ping | tr -d "\r\n")"
    [[ "$redis_reply" == "PONG" ]] || { echo "Redis smoke check failed" >&2; exit 1; }
    for service in identity trust registry; do
      cid="$("${COMPOSE[@]}" ps -q "$service")"
      [[ -n "$cid" ]] || { echo "Missing staging service: $service" >&2; exit 1; }
      state="$(docker inspect --format "{{.State.Status}}" "$cid")"
      [[ "$state" == "running" ]] || { echo "Staging service not running: $service ($state)" >&2; exit 1; }
    done
    for service in identity trust registry; do
      "${COMPOSE[@]}" exec -T "$service" python -c 'import json,urllib.request,sys; d=json.load(urllib.request.urlopen("http://127.0.0.1:8000/health",timeout=8)); assert d.get("status")=="ok" and d.get("service")==sys.argv[1],d; print("PASS: HTTP health",sys.argv[1])' "$service"
    done
    echo "PASS: staging PostgreSQL, Redis, and application HTTP health endpoints respond"
    bash deploy/oci/monitor-staging.sh
    ;;
  --start)
    echo "Staging startup is a controlled change on the selected Ubuntu host."
    [[ "${AEPX_STAGING_APPROVED:-}" == "yes" ]] || {
      echo "BLOCKED: set AEPX_STAGING_APPROVED=yes only after confirming the target is NOT the production host." >&2
      exit 3
    }
    python3 deploy/oci/validate-scoped-credentials.py
    python3 deploy/oci/check-staging-policy.py
    python3 deploy/oci/verify-image-platforms.py
    bash deploy/oci/verify-release-gates.sh
    [[ "${AEPX_BACKUP_RESTORE_VERIFIED:-}" == "yes" ]] || {
      echo "BLOCKED: isolated backup restore evidence required" >&2
      exit 3
    }
    [[ "${AEPX_IMAGE_PLATFORMS_VERIFIED:-}" == "yes" ]] || {
      echo "BLOCKED: target architecture image verification required" >&2
      exit 3
    }
    python3 deploy/oci/validate-release-evidence.py
    echo "Starting isolated staging Compose project (no host ports)."
    "${COMPOSE[@]}" up -d --build
    "${COMPOSE[@]}" ps
    ;;
  *)
    echo "Usage: $0 [--validate|--status|--logs|--smoke|--db-smoke|--db-commit|--start|--stop]" >&2
    exit 2
    ;;
esac
