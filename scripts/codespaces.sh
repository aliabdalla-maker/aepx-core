#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
MODE="${1:-status}"
COMPOSE=(docker compose -f compose.codespaces.yml)
case "$MODE" in
  start)
    for i in $(seq 1 40); do docker info >/dev/null 2>&1 && break; sleep 3; done
    docker info >/dev/null || { echo "Docker daemon unavailable"; exit 1; }
    "${COMPOSE[@]}" config --quiet
    "${COMPOSE[@]}" up -d --build
    bash scripts/codespaces-verify.sh
    ;;
  verify) bash scripts/codespaces-verify.sh ;;
  status) "${COMPOSE[@]}" ps ;;
  logs) "${COMPOSE[@]}" logs --tail=150 ;;
  stop) "${COMPOSE[@]}" down ;;
  full)
    echo "Full stack requires a larger Codespace and security review."
    echo "Run manually only after reviewing published ports and development credentials:"
    echo "docker compose -f docker-compose.yml up -d --build"
    ;;
  *) echo "Usage: bash scripts/codespaces.sh {start|verify|status|logs|stop|full}"; exit 2 ;;
esac
