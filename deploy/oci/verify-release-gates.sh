#!/usr/bin/env bash
set -Eeuo pipefail
# Fail-closed readiness verification; no installs, firewall changes, or containers started.
cd "$(dirname "$0")/../.."
fail=0
check() {
  if "$@"; then printf 'PASS: %s\n' "$1"; else printf 'BLOCKED: %s\n' "$1" >&2; fail=1; fi
}
is_ubuntu() { grep -q '^ID=ubuntu$' /etc/os-release; }
has_docker() { command -v docker >/dev/null && docker compose version >/dev/null; }
has_memory() {
  local kb
  kb="$(awk '/MemTotal:/ {print $2}' /proc/meminfo)"
  [[ "${kb:-0}" -ge 3500000 ]]
}
has_disk() { [[ "$(df -Pk . | awk 'NR==2 {print $4}')" -ge 10000000 ]]; }
has_secrets() { python3 deploy/oci/validate-secrets.py; }
has_private_compose() { bash deploy/oci/deploy.sh --validate-only; }
check is_ubuntu
check has_docker
check has_memory
check has_disk
check has_secrets
check has_private_compose
if (( fail )); then
  echo "RELEASE BLOCKED. No changes made." >&2
  exit 1
fi
echo "Static host checks passed; runtime architecture, backups, TLS, and acceptance tests still required."
