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
    echo "Refusing automatic start: host inventory, backups and image compatibility must be verified."
    echo "After independent approval, run the isolated compose command manually on the staging VM."
    exit 3
    ;;
  *)
    echo "Usage: $0 [--validate|--status|--smoke|--start]" >&2
    exit 2
    ;;
esac
