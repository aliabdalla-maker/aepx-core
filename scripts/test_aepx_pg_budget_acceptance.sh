#!/usr/bin/env bash
# Explicit opt-in, disposable PostgreSQL database ONLY. Never apply migrations here.
set -euo pipefail
if [[ "${1:-}" != "--execute" || $# -ne 2 ]]; then
  echo "Usage: $0 --execute aepx_test_<dedicated_database_name>" >&2
  exit 2
fi
db="$2"
if [[ ! "$db" =~ ^aepx_test_[a-z0-9_]{1,40}$ ]]; then
  echo "Refusing non-test database name" >&2
  exit 2
fi
if [[ -n "${PGHOST:-}" && "${PGHOST}" != "localhost" && "${PGHOST}" != "127.0.0.1" && "${PGHOST}" != "/var/run/postgresql" ]]; then
  echo "Refusing nonlocal PostgreSQL host" >&2
  exit 2
fi
if [[ -n "${PGSERVICE:-}" || -n "${PGSERVICEFILE:-}" || -n "${PGDATABASE:-}" || -n "${PGHOSTADDR:-}" ]]; then
  echo "Unset PGSERVICE, PGSERVICEFILE, PGDATABASE and PGHOSTADDR" >&2
  exit 2
fi
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
PGHOST=127.0.0.1 psql -X -v ON_ERROR_STOP=1 --dbname="$db" \
  --file="$root/tests/sql/aepx_budget_pg_acceptance.sql"
