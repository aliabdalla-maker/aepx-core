#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
echo "== AEP-X Codespaces smoke test =="
docker info >/dev/null
docker compose -f compose.codespaces.yml config --quiet
curl --fail --silent --show-error --max-time 10 http://127.0.0.1:8083/openapi.json | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("openapi") and "AEP-X" in d.get("info",{}).get("title",""), d; print("PASS: console OpenAPI")'
if [[ "${1:-}" == "--core" ]]; then
  docker compose -f docker-compose.yml -f compose.codespaces-core.yml config --quiet
  for service in postgres redis identity trust registry memory cache governance gateway; do
    container="$(docker compose -f docker-compose.yml -f compose.codespaces-core.yml ps -q "$service")"
    [[ -n "$container" ]] || { echo "FAIL: $service has no container"; exit 1; }
    state="$(docker inspect -f '{{.State.Status}}' "$container")"
    [[ "$state" == running ]] || { echo "FAIL: $service is $state"; exit 1; }
    echo "PASS: $service container running"
  done
  for service in gateway identity trust registry memory cache governance; do
    if docker compose -f docker-compose.yml -f compose.codespaces-core.yml exec -T "$service" python -c 'import urllib.request; urllib.request.urlopen("http://localhost:8000/openapi.json",timeout=8)' >/dev/null 2>&1; then
      echo "PASS: $service HTTP"
    else
      echo "FAIL: $service HTTP"; exit 1
    fi
  done
fi
