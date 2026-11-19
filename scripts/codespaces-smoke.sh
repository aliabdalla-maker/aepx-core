#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
echo "== AEP-X Codespaces smoke test =="
docker info >/dev/null
docker compose -f compose.codespaces.yml config --quiet

# Retry startup races, fail on invalid HTTP/JSON, and preserve diagnostic details.
python3 - <<'PY'
import json, time, urllib.request, urllib.error, sys
url="http://127.0.0.1:8083/openapi.json"
last_error=""
for attempt in range(1, 31):
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            status=response.status
            body=response.read(1024*1024)
            if status != 200:
                raise RuntimeError(f"HTTP {status}: {body[:300]!r}")
            if not body:
                raise RuntimeError("HTTP 200 with empty body")
            data=json.loads(body)
            if not isinstance(data, dict) or not data.get("openapi") or not data.get("info",{}).get("title"):
                raise RuntimeError(f"Unexpected OpenAPI document: {body[:300]!r}")
            print(f"PASS: console OpenAPI HTTP {status}; title={data['info']['title']!r}; attempt={attempt}")
            break
    except Exception as exc:
        last_error=f"{type(exc).__name__}: {exc}"
        print(f"Waiting for console ({attempt}/30): {last_error}", file=sys.stderr)
        if attempt == 30:
            print(f"FAIL: console did not return valid OpenAPI JSON: {last_error}", file=sys.stderr)
            sys.exit(1)
        time.sleep(2)
PY

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
