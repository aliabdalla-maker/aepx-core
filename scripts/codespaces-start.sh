#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
LOG="/tmp/aepx-codespaces-startup.log"
exec > >(tee -a "$LOG") 2>&1
echo "== Starting AEP-X console in Codespaces =="
for i in $(seq 1 40); do
  if docker info >/dev/null 2>&1; then break; fi
  sleep 3
done
docker info >/dev/null || { echo "Docker daemon not ready"; exit 1; }
docker compose -f compose.codespaces.yml config --quiet
docker compose -f compose.codespaces.yml up -d --build
bash scripts/codespaces-verify.sh
echo "AEP-X console ready on port 8083 (Codespaces Ports tab, Private)."
