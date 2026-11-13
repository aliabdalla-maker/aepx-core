#!/usr/bin/env bash
set -Eeuo pipefail
# Run from the repository root on the OCI host.
cd "$(dirname "$0")/../.."
command -v docker >/dev/null
docker compose version >/dev/null
[[ -f docker-compose.yml ]] || { echo "Missing docker-compose.yml"; exit 1; }
[[ -f .env ]] || { echo "Missing .env; create locally with chmod 600"; exit 1; }
# Generate a security overlay for EVERY service exposing ports.
# Published ports are bound only to localhost, never OCI public interfaces.
python3 - <<'PY'
import re
from pathlib import Path
s=Path('docker-compose.yml').read_text()
services={}
name=None
in_services=False
for line in s.splitlines():
    if line.strip()=='services:':
        in_services=True
        continue
    if not in_services: continue
    m=re.match(r'^  ([a-zA-Z0-9_-]+):\s*$',line)
    if m: name=m.group(1)
    if name and re.match(r'^    ports:',line):
        ports=re.findall(r'["\'](\d+):(\d+)["\']',line)
        if not ports:
            raise SystemExit(f'Unsupported ports syntax for {name}; refusing unsafe deployment')
        services[name]=ports
out=['# Generated; do not commit. All host ports loopback-only.','services:']
for name,ports in services.items():
    out.append(f'  {name}:')
    out.append('    ports: !override')
    for host,container in ports:
        out.append(f'      - "127.0.0.1:{host}:{container}"')
out.extend(['  postgres:','    environment:','      POSTGRES_PASSWORD: ${AEPX_POSTGRES_PASSWORD:?Set AEPX_POSTGRES_PASSWORD}','    volumes: !override','      - postgres-data:/var/lib/postgresql/data','      - ./schemas/sql:/docker-entrypoint-initdb.d:ro','  trust:','    environment:','      DATABASE_URL: postgresql://aepx:${AEPX_POSTGRES_PASSWORD:?Set AEPX_POSTGRES_PASSWORD}@postgres:5432/aepx','  registry:','    environment:','      DATABASE_URL: postgresql://aepx:${AEPX_POSTGRES_PASSWORD:?Set AEPX_POSTGRES_PASSWORD}@postgres:5432/aepx','      IDENTITY_URL: http://identity:8000','  governance:','    environment:','      DATABASE_URL: postgresql://aepx:${AEPX_POSTGRES_PASSWORD:?Set AEPX_POSTGRES_PASSWORD}@postgres:5432/aepx','  brain:','    environment:','      DATABASE_URL: postgresql://aepx:${AEPX_POSTGRES_PASSWORD:?Set AEPX_POSTGRES_PASSWORD}@postgres:5432/aepx','  neo4j:','    environment:','      NEO4J_AUTH: neo4j/${AEPX_NEO4J_PASSWORD:?Set AEPX_NEO4J_PASSWORD}','volumes:','  postgres-data:'])
Path('deploy/oci/compose.secure.generated.yml').write_text('\n'.join(out)+'\n')
print('Loopback overlay generated for',len(services),'published services')
PY
set -a
source .env
set +a
docker compose -f docker-compose.yml -f deploy/oci/compose.secure.generated.yml config --quiet
docker compose -f docker-compose.yml -f deploy/oci/compose.secure.generated.yml up -d --build
docker compose -f docker-compose.yml -f deploy/oci/compose.secure.generated.yml ps
curl --fail --silent --show-error --max-time 15 http://127.0.0.1:8000/health || echo "Gateway not healthy yet; inspect docker compose logs"
echo "Private OCI deployment complete. Public access is intentionally disabled pending authentication and HTTPS review."
