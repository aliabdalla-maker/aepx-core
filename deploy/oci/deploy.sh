#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/../.."
command -v docker >/dev/null
docker compose version >/dev/null
command -v python3 >/dev/null
[[ -f .env ]] || { echo "Create a private .env file first"; exit 1; }
[[ "$(stat -c %a .env)" == "600" ]] || { echo "Set chmod 600 .env"; exit 1; }
# Do not source arbitrary shell code from .env. Docker Compose reads it itself.
# Generate override from Compose's parsed JSON, including multi-line ports.
docker compose -f docker-compose.yml config --format json > /tmp/aepx-compose-$$.json
trap 'rm -f /tmp/aepx-compose-$$.json' EXIT
python3 - /tmp/aepx-compose-$$.json <<'PY'
import json,sys
from pathlib import Path
cfg=json.load(open(sys.argv[1]))
out=["# Generated for OCI private deployment","services:"]
for name,service in cfg["services"].items():
    ports=service.get("ports",[])
    if not ports: continue
    out += [f"  {name}:", "    ports: !override"]
    for port in ports:
        target=port["target"]
        published=port.get("published",target)
        protocol=port.get("protocol","tcp")
        if protocol != "tcp":
            raise SystemExit(f"Review non-TCP port {name}: {protocol}")
        out.append(f'      - "127.0.0.1:{published}:{target}"')
out += [
"  postgres:",
"    environment:",
"      POSTGRES_PASSWORD: ${AEPX_POSTGRES_PASSWORD:?Missing password}",
"    volumes: !override",
"      - postgres-data:/var/lib/postgresql/data",
"      - ./schemas/sql:/docker-entrypoint-initdb.d:ro",
"  trust:",
"    environment:",
"      DATABASE_URL: postgresql://aepx:${AEPX_POSTGRES_PASSWORD:?Missing password}@postgres:5432/aepx",
"  registry:",
"    environment:",
"      DATABASE_URL: postgresql://aepx:${AEPX_POSTGRES_PASSWORD:?Missing password}@postgres:5432/aepx",
"  governance:",
"    environment:",
"      DATABASE_URL: postgresql://aepx:${AEPX_POSTGRES_PASSWORD:?Missing password}@postgres:5432/aepx",
"  brain:",
"    environment:",
"      DATABASE_URL: postgresql://aepx:${AEPX_POSTGRES_PASSWORD:?Missing password}@postgres:5432/aepx",
"  neo4j:",
"    environment:",
"      NEO4J_AUTH: neo4j/${AEPX_NEO4J_PASSWORD:?Missing password}",
"volumes:",
"  postgres-data:"
]
p=Path("deploy/oci/compose.secure.generated.yml")
p.write_text("\n".join(out)+"\n")
print(f"Generated private overlay for {len(cfg['services'])} services")
PY
docker compose -f docker-compose.yml -f deploy/oci/compose.secure.generated.yml config --quiet
if [[ "${1:-}" == "--validate-only" ]]; then echo "Compose validated; no containers started"; exit 0; fi
echo "Refusing to deploy without explicit --deploy; this is a fresh-install workflow."
[[ "${1:-}" == "--deploy" ]] || exit 2
docker compose -f docker-compose.yml -f deploy/oci/compose.secure.generated.yml up -d --build
docker compose -f docker-compose.yml -f deploy/oci/compose.secure.generated.yml ps
curl -fsS --max-time 15 http://127.0.0.1:8000/health
