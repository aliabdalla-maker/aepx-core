#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
echo "[AEP-X] OCI Always Free staging preflight (read-only)"
test -f deploy/oci-always-free/compose.yml
command -v docker >/dev/null || { echo "Docker missing" >&2; exit 1; }
docker compose version >/dev/null
test -n "${AEPX_POSTGRES_PASSWORD:-}" || { echo "AEPX_POSTGRES_PASSWORD must be supplied securely" >&2; exit 1; }
test "${#AEPX_POSTGRES_PASSWORD}" -ge 24 || { echo "Database password must have at least 24 characters" >&2; exit 1; }
python3 scripts/aepx-oci-compose-guard.py
echo "Preflight passed. No containers created. Review docs before manual staging deployment."
