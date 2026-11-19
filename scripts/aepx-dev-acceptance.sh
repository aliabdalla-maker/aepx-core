#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
mkdir -p artifacts
echo "AEP-X private development acceptance: console + core; no production deployment"
bash scripts/codespaces.sh diagnose
bash scripts/codespaces.sh start
bash scripts/aepx-release-audit.sh
if [[ "${1:-}" == "--core" ]]; then
  echo "WARNING: core Compose publishes development ports and uses development credentials."
  echo "Only run in a PRIVATE Codespace; do not forward core ports publicly."
  bash scripts/codespaces.sh core
  python3 scripts/aepx-core-integration.py
fi
python3 scripts/aepx-progress.py --output artifacts/aepx-progress.md
echo "Acceptance evidence written under artifacts/"
