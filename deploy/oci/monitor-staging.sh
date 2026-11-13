#!/usr/bin/env bash
set -Eeuo pipefail
# Read-only staging monitor for cron/systemd; does not restart containers.
cd "$(dirname "$0")/../.."
umask 077
[[ -f .env ]] || { echo "CRITICAL: private .env missing" >&2; exit 2; }
COMPOSE=(docker compose --env-file .env -p aepx-oci-staging -f deploy/oci/compose.staging.yml)
failed=0
for service in postgres redis identity trust registry; do
  cid="$("${COMPOSE[@]}" ps -q "$service" 2>/dev/null || true)"
  if [[ -z "$cid" ]]; then
    echo "CRITICAL: $service missing"; failed=1; continue
  fi
  state="$(docker inspect -f '{{.State.Status}}' "$cid" 2>/dev/null || true)"
  if [[ "$state" != running ]]; then
    echo "CRITICAL: $service state=$state"; failed=1; continue
  fi
  health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}not-configured{{end}}' "$cid")"
  if [[ "$health" == unhealthy || "$health" == starting ]]; then
    echo "CRITICAL: $service health=$health"; failed=1
  else
    echo "OK: $service running health=$health"
  fi
done
if [[ "$failed" -ne 0 ]]; then
  echo "ALERT: isolated AEP-X staging unhealthy" >&2
  exit 1
fi
echo "PASS: isolated AEP-X staging container availability"
