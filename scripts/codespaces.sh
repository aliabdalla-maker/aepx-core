#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
MODE="${1:-status}"
COMPOSE=(docker compose -f compose.codespaces.yml)
FULL=(docker compose -f docker-compose.yml)
CORE=(postgres redis identity trust registry memory cache governance gateway)
ensure_docker() {
  for i in $(seq 1 40); do docker info >/dev/null 2>&1 && return 0; sleep 3; done
  echo "ERROR: Docker daemon unavailable" >&2; return 1
}
case "$MODE" in
  start)
    ensure_docker
    "${COMPOSE[@]}" config --quiet
    "${COMPOSE[@]}" up -d --build
    bash scripts/codespaces-verify.sh
    ;;
  verify) bash scripts/codespaces-verify.sh ;;
  status) "${COMPOSE[@]}" ps ;;
  logs) "${COMPOSE[@]}" logs --tail=150 ;;
  stop) "${COMPOSE[@]}" down ;;
  core)
    ensure_docker
    echo "WARNING: Existing full-stack Compose exposes service ports and uses development credentials."
    echo "Start only in a PRIVATE Codespace; never make backend ports public."
    "${FULL[@]}" config --quiet
    "${FULL[@]}" up -d --build "${CORE[@]}"
    "${FULL[@]}" ps "${CORE[@]}"
    ;;
  core-status) "${FULL[@]}" ps "${CORE[@]}" ;;
  core-logs) "${FULL[@]}" logs --tail=120 "${CORE[@]}" ;;
  core-stop) "${FULL[@]}" stop "${CORE[@]}" ;;
  full)
    echo "Full stack needs a larger Codespace and a security review."
    echo "For a targeted core deployment, run: bash scripts/codespaces.sh core"
    ;;
  diagnose)
    echo "== Docker =="; docker info --format '{{.ServerVersion}}' || true
    echo "== Disk =="; df -h . || true
    echo "== Memory =="; free -h || true
    echo "== Console =="; "${COMPOSE[@]}" ps || true
    echo "== HTTP =="; curl -fsS -o /dev/null -w 'HTTP %{http_code}\n' http://127.0.0.1:8083/openapi.json || true
    echo "== Logs =="; "${COMPOSE[@]}" logs --tail=80 || true
    ;;
  *) echo "Usage: bash scripts/codespaces.sh {start|verify|status|logs|stop|core|core-status|core-logs|core-stop|full|diagnose}"; exit 2 ;;
esac
