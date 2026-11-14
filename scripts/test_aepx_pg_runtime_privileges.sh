#!/usr/bin/env bash
# Read-only, opt-in localhost audit of the actual runtime role.
set -euo pipefail
if [[ $# -ne 2 || "${1:-}" != "--execute" || ! "${2:-}" =~ ^aepx_test_[a-z0-9_]{1,40}$ ]]; then
  echo "Usage: $0 --execute aepx_test_<database>" >&2
  exit 2
fi
for variable in PGSERVICE PGSERVICEFILE PGDATABASE PGHOSTADDR PGOPTIONS; do
  if [[ -n "${!variable:-}" ]]; then
    echo "Unset $variable before running" >&2
    exit 2
  fi
done
if [[ -n "${PGHOST:-}" && "${PGHOST}" != "localhost" && "${PGHOST}" != "127.0.0.1" ]]; then
  echo "Remote PGHOST refused" >&2
  exit 2
fi
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
# PostgreSQL read-only transaction: no migration, no changes.
PGHOST=127.0.0.1 PGOPTIONS='-c default_transaction_read_only=on' \
  psql -X -v ON_ERROR_STOP=1 --dbname="$2" \
  --file="$root/tests/sql/aepx_runtime_role_privilege_audit.sql"
