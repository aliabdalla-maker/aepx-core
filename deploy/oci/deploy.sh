#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/../.."
command -v docker >/dev/null
docker compose version >/dev/null
command -v python3 >/dev/null
[[ -f .env ]] || { echo "Create a private .env file first"; exit 1; }
[[ "$(stat -c %a .env)" == "600" ]] || { echo "Run chmod 600 .env"; exit 1; }
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
docker compose -f docker-compose.yml config --format json > "$TMP"
python3 - "$TMP" <<'PY'
import json, sys
from pathlib import Path
cfg=json.load(open(sys.argv[1]))
services={}
for name, service in cfg["services"].items():
    ports=service.get("ports",[])
    if not ports: continue
    lines=["    ports: !override"]
    for port in ports:
        if port.get("protocol","tcp")!="tcp":
            raise SystemExit(f"Unsupported protocol for {name}")
        target=port["target"]
        published=port.get("published",target)
        if not str(published).isdigit():
            raise SystemExit(f"Non-static port for {name}: {published}")
        lines.append(f'      - "127.0.0.1:{published}:{target}"')
    services[name]=lines
extra={
 "postgres": [
  "    environment:",
  "      POSTGRES_PASSWORD: ${AEPX_POSTGRES_PASSWORD:?Missing password}",
  "    volumes: !override",
  "      - postgres-data:/var/lib/postgresql/data",
  "      - ./schemas/sql:/docker-entrypoint-initdb.d:ro"],
 "trust": ["    environment:", "      DATABASE_URL: postgresql://aepx:${AEPX_POSTGRES_PASSWORD:?Missing password}@postgres:5432/aepx"],
 "registry": ["    environment:", "      DATABASE_URL: postgresql://aepx:${AEPX_POSTGRES_PASSWORD:?Missing password}@postgres:5432/aepx"],
 "governance": ["    environment:", "      DATABASE_URL: postgresql://aepx:${AEPX_POSTGRES_PASSWORD:?Missing password}@postgres:5432/aepx"],
 "brain": ["    environment:", "      DATABASE_URL: postgresql://aepx:${AEPX_POSTGRES_PASSWORD:?Missing password}@postgres:5432/aepx"],
 "neo4j": ["    environment:", "      NEO4J_AUTH: neo4j/${AEPX_NEO4J_PASSWORD:?Missing password}"]
}
for name,lines in extra.items():
    if name not in cfg["services"]:
        raise SystemExit(f"Expected service absent: {name}")
    services.setdefault(name,[]).extend(lines)
out=["# Generated OCI private overlay","services:"]
for name,lines in services.items():
    out.append(f"  {name}:")
    out.extend(lines)
out.extend(["volumes:","  postgres-data:"])
Path("deploy/oci/compose.secure.generated.yml").write_text("\n".join(out)+"\n")
print("Generated unique service entries:",len(services))
PY
docker compose -f docker-compose.yml -f deploy/oci/compose.secure.generated.yml config --quiet
python3 deploy/oci/preflight.py
if [[ "${1:-}" == "--validate-only" ]]; then
  echo "Validation complete; no containers started"
  exit 0
fi
[[ "${1:-}" == "--deploy" ]] || { echo "Use --validate-only; --deploy requires explicit approval"; exit 2; }
echo "Deployment disabled until production credentials, architecture and backup gates are cleared."
exit 3
