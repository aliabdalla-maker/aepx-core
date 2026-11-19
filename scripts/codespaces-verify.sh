#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
echo "== AEP-X Codespaces checks =="
command -v docker >/dev/null || { echo "Docker is unavailable"; exit 1; }
docker info >/dev/null || { echo "Docker daemon unavailable"; exit 1; }
docker compose version
docker compose -f compose.codespaces.yml config --quiet
echo "Docker and Compose configuration OK"
if [[ "${1:-}" == "--prerequisites" ]]; then
  echo "Ready: run docker compose -f compose.codespaces.yml up -d --build"
  exit 0
fi
docker compose -f compose.codespaces.yml ps
for attempt in $(seq 1 30); do
  if curl -fsS -o /dev/null http://127.0.0.1:8083/openapi.json; then
    echo "PASS: console OpenAPI responds on localhost:8083"
    echo "Note: backend services are not started in lightweight mode."
    exit 0
  fi
  sleep 2
done
echo "FAIL: console did not respond; recent logs:"
docker compose -f compose.codespaces.yml logs --tail=80 aepx-console
exit 1
