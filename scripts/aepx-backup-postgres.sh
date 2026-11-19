#!/usr/bin/env bash
# Private development backup. No restore into a running database.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
umask 077
dest="${AEPX_BACKUP_DIR:-artifacts/backups}"
mkdir -p "$dest"
chmod 700 "$dest"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
out="$dest/aepx-postgres-$stamp.dump"
tmp="$out.partial"
trap 'rm -f "$tmp"' EXIT
docker compose -f docker-compose.yml -f compose.codespaces-core.yml exec -T postgres sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$tmp"
[[ -s "$tmp" ]] || { echo "FAIL: empty backup" >&2; exit 1; }
if command -v pg_restore >/dev/null 2>&1; then pg_restore --list "$tmp" >/dev/null; fi
mv "$tmp" "$out"
sha256sum "$out" > "$out.sha256"
echo "Backup saved locally: $out"
echo "WARNING: backup contains sensitive database content. Encrypt before transfer, set retention, and perform an isolated restore drill."
