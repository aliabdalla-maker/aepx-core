#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/../.."
COMPOSE=(docker compose -p aepx-oci-staging -f deploy/oci/compose.staging.yml)
case "${1:---validate}" in
  --validate)
    python3 deploy/oci/validate-secrets.py
    "${COMPOSE[@]}" config --quiet
    python3 - <<'PY'
import json,subprocess
cfg=json.loads(subprocess.check_output(["docker","compose","-p","aepx-oci-staging","-f","deploy/oci/compose.staging.yml","config","--format","json"],text=True))
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
  --smoke)
    "${COMPOSE[@]}" ps --status running
    "${COMPOSE[@]}" exec -T postgres pg_isready -U aepx -d aepx
    "${COMPOSE[@]}" exec -T redis redis-cli ping
    for service in identity trust registry; do
      [[ -n "$("${COMPOSE[@]}" ps -q "$service")" ]] || { echo "Missing staging service: $service" >&2; exit 1; }
    done
    echo "PASS: staging PostgreSQL and Redis respond; application HTTP acceptance tests still required"
    ;;
  --start)
    echo "Staging startup is a controlled change on the selected Ubuntu host."
    [[ "${AEPX_STAGING_APPROVED:-}" == "yes" ]] || {
      echo "BLOCKED: set AEPX_STAGING_APPROVED=yes only after confirming the target is NOT the production host." >&2
      exit 3
    }
    bash deploy/oci/verify-release-gates.sh
    [[ "${AEPX_BACKUP_RESTORE_VERIFIED:-}" == "yes" ]] || {
      echo "BLOCKED: isolated backup restore evidence required" >&2
      exit 3
    }
    [[ "${AEPX_IMAGE_PLATFORMS_VERIFIED:-}" == "yes" ]] || {
      echo "BLOCKED: target architecture image verification required" >&2
      exit 3
    }
    echo "Starting isolated staging Compose project (no host ports)."
    "${COMPOSE[@]}" up -d --build
    "${COMPOSE[@]}" ps
    ;;
  *)
    echo "Usage: $0 [--validate|--status|--smoke|--start]" >&2
    exit 2
    ;;
esac
