#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/../.."
umask 077
[[ -f deploy/oci/compose.secure.generated.yml ]] || { echo "Generate overlay first"; exit 1; }
BACKUP_DIR="${BACKUP_DIR:-/opt/aepx-backups}"
mkdir -p "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="$BACKUP_DIR/aepx-$STAMP.sql.gz"
docker compose -f docker-compose.yml -f deploy/oci/compose.secure.generated.yml exec -T postgres pg_dump -U aepx -d aepx | gzip -9 > "$DEST"
test -s "$DEST"
gzip -t "$DEST"
sha256sum "$DEST" > "$DEST.sha256"
echo "Created local backup: $DEST"
echo "IMPORTANT: Transfer securely to encrypted off-host storage and test restoration. Local-only backups do not protect against VM loss."
