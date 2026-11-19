#!/bin/sh
# Applies control-plane migrations that are not yet recorded in aav.schema_migrations, each in one
# transaction. Runs inside the postgres container:  docker compose exec -T postgres sh -s < migrate.sh
# Safe to re-run. A database created before this runner existed has 001 and 002 marked as applied.
set -eu
P="psql -v ON_ERROR_STOP=1 -U ${POSTGRES_USER:-aav_owner} -d ${POSTGRES_DB:-aav}"
$P -q <<'SQL'
CREATE TABLE IF NOT EXISTS aav.schema_migrations (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now());
INSERT INTO aav.schema_migrations (name)
  SELECT n FROM (VALUES ('001_init.sql'), ('002_updates.sql')) v(n)
  WHERE to_regclass('aav.update_bundles') IS NOT NULL ON CONFLICT DO NOTHING;
SQL
for f in /migrations/*.sql; do
  n=$(basename "$f")
  if [ -z "$($P -tA -c "SELECT 1 FROM aav.schema_migrations WHERE name = '$n'")" ]; then
    $P --single-transaction -q -f "$f"
    $P -q -c "INSERT INTO aav.schema_migrations (name) VALUES ('$n')"
    echo "applied $n"
  fi
done
echo "migrations up to date"
