#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
mkdir -p artifacts
python3 scripts/aepx-static-security.py
python3 scripts/aepx-compose-exposure.py
python3 -m unittest discover -s tests -p 'test_aepx_core_integration.py' -v
python3 scripts/aepx-progress.py --validate
echo "Static evidence complete. Live integration, restore drill and production signoff remain separate."
