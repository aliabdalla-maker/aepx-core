#!/usr/bin/env bash
# Encrypted logical backup (OCI-10). Stores on the VM's boot/block volume within Always Free storage.
# Requires AAV_BACKUP_PASSPHRASE_FILE (mode 600). Keeps the last 14 backups.
set -euo pipefail
cd "${AAV_COMPOSE_DIR:-$(dirname "$0")}"   # compose files (and COMPOSE_FILE/COMPOSE_PROJECT_NAME) select the stack
OUT=${AAV_BACKUP_DIR:-/var/backups/aav}; mkdir -p "$OUT"; chmod 700 "$OUT"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
docker compose exec -T postgres pg_dump -U aav_owner -d aav --format=custom \
  | openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -salt -pass "file:${AAV_BACKUP_PASSPHRASE_FILE:?}" > "$OUT/aav-$STAMP.dump.enc"
sha256sum "$OUT/aav-$STAMP.dump.enc" > "$OUT/aav-$STAMP.dump.enc.sha256"
ls -1t "$OUT"/aav-*.dump.enc | tail -n +15 | xargs -r -I{} sh -c 'rm -f "{}" "{}.sha256"'
echo "backup written: $OUT/aav-$STAMP.dump.enc"
# Off-VM copy to OCI Object Storage (BE-05, OCI-10) when a bucket is configured; the file is already encrypted.
if [ -n "${AAV_OBJECT_STORE_BUCKET:-}" ]; then
  docker compose exec -T control-plane python -m app.admin store-backup "aav-$STAMP.dump.enc" < "$OUT/aav-$STAMP.dump.enc" \
    && echo "off-VM copy stored in bucket $AAV_OBJECT_STORE_BUCKET" \
    || echo "WARNING: off-VM copy failed; the local backup is intact" >&2
fi
