#!/usr/bin/env bash
set -Eeuo pipefail
# Safe read-only host readiness report. Does not install or deploy.
echo "Architecture: $(uname -m)"
echo "OS:"
grep -E '^(NAME|VERSION_ID)=' /etc/os-release || true
echo "CPU: $(nproc)"
echo "RAM:"
free -h
echo "Root disk:"
df -h /
echo "Ports 80/443/8000/8083:"
if command -v ss >/dev/null; then ss -lnt '( sport = :80 or sport = :443 or sport = :8000 or sport = :8083 )'; fi
if command -v docker >/dev/null; then
  echo "Docker:"
  docker version --format '{{.Server.Version}}' || true
  docker compose version || true
else
  echo "Docker not installed"
fi
echo "No services or firewall rules changed."
