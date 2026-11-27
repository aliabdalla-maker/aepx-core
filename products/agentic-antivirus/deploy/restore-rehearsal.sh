#!/usr/bin/env bash
# Restores an encrypted backup into a throwaway PostgreSQL container and checks it (OCI-10, RA-12). Never touches
# the live database. Verifies the checksum, decrypts, restores, compares row counts of the key tables with the
# live database (when it is reachable), and writes timed evidence.
#   restore-rehearsal.sh BACKUP.dump.enc
# Evidence: $AAV_EVIDENCE_DIR/restore-<UTC>.json (default /var/lib/aav/evidence).
set -euo pipefail
FILE=${1:?usage: restore-rehearsal.sh BACKUP.dump.enc}
EVID=${AAV_EVIDENCE_DIR:-/var/lib/aav/evidence}; mkdir -p "$EVID"
PGIMAGE=${AAV_REHEARSAL_PG_IMAGE:-postgres:16-alpine}
TABLES="tenants users devices incidents audit_log update_bundles"
T0=$(date +%s)
sha256sum -c "$FILE.sha256"
NAME=aav-restore-$$
docker run -d --rm --name "$NAME" -e POSTGRES_PASSWORD=rehearsal -e POSTGRES_DB=aav "$PGIMAGE" >/dev/null
trap 'docker stop "$NAME" >/dev/null 2>&1 || true' EXIT
until docker exec "$NAME" pg_isready -U postgres >/dev/null 2>&1; do sleep 1; done
docker exec "$NAME" psql -U postgres -d aav -c "CREATE ROLE aav_app LOGIN; CREATE ROLE aav_owner LOGIN" >/dev/null
openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -pass "file:${AAV_BACKUP_PASSPHRASE_FILE:?}" -in "$FILE" \
  | docker exec -i "$NAME" pg_restore -U postgres -d aav --no-owner --exit-on-error
T1=$(date +%s)
count() {  # count CONTAINER_CMD... TABLE
  local t=${*: -1}; set -- "${@:1:$(($#-1))}"
  "$@" -tAc "SELECT count(*) FROM aav.$t" 2>/dev/null || echo "n/a"
}
ROWS=""; ALLOK=true
for t in $TABLES; do
  r=$(count docker exec "$NAME" psql -U postgres -d aav "$t")
  l=$( (cd "${AAV_COMPOSE_DIR:-$(dirname "$0")}" && count docker compose exec -T postgres psql -U aav_owner -d aav "$t") || echo "n/a")
  [ "$r" = "n/a" ] && ALLOK=false
  ROWS="$ROWS{\"table\": \"$t\", \"restored\": \"$r\", \"live_now\": \"$l\"},"
  echo "$t restored=$r live_now=$l"
done
[ "$(count docker exec "$NAME" psql -U postgres -d aav tenants)" -ge 1 ] 2>/dev/null || ALLOK=false
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT="$EVID/restore-$STAMP.json"
cat > "$OUT" <<JSON
{"rehearsal": "restore", "at": "$STAMP", "backup": "$(basename "$FILE")",
 "backup_bytes": $(stat -c %s "$FILE"), "restore_seconds": $((T1 - T0)),
 "tables": [${ROWS%,}], "passed": $ALLOK}
JSON
cat "$OUT"
$ALLOK && echo "restore rehearsal passed" || { echo "restore rehearsal FAILED" >&2; exit 1; }
