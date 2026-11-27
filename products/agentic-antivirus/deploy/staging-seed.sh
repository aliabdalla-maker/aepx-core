#!/usr/bin/env bash
# Loads synthetic, sanitised data into STAGING only (OCI-16): one fictional tenant, two enrolled devices
# driven by the real agent, a credential-dumping incident and its investigation. No production data is copied.
# Run ON the VM after `deploy.sh SHA staging`. Needs python3 with httpx + the agent's requirements
# (created once in /opt/aav-tools).
set -euo pipefail
cd "$(dirname "$0")"
VENV=${AAV_TOOLS_VENV:-/opt/aav-tools}
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q httpx -r ../agent/requirements.txt
fi
export AAV_API=http://127.0.0.1:18481/api
export AAV_PSQL_CMD="docker compose -p agentic-antivirus-staging -f compose.yml -f compose.staging.yml exec -T postgres psql -U aav_owner -d aav"
set -a; . "${AAV_ENV_FILE:-/etc/aav/aav-staging.env}"; set +a
curl -fsS "$AAV_API/health" | grep -q '"environment":"staging"' || { echo "refusing: $AAV_API is not staging" >&2; exit 1; }
"$VENV/bin/python" ../tools/seed_demo.py
echo "staging seeded with synthetic data"
