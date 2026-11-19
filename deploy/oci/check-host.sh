#!/usr/bin/env bash
set -Eeuo pipefail
echo "Architecture: $(uname -m)"
echo "Disk:"
df -h /
echo "Memory:"
free -h
echo "Docker:"
docker version --format '{{.Server.Version}}'
docker compose version
echo "Bound TCP sockets:"
sudo ss -lntp
echo "Gateway:"
curl -fsS --max-time 15 http://127.0.0.1:8000/health
