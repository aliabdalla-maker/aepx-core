#!/usr/bin/env bash
# Restores a backup into a throwaway container and runs integrity checks (RA-12). Never touches the live DB.
set -euo pipefail
FILE=${1:?usage: restore-rehearsal.sh BACKUP.dump.enc}
sha256sum -c "$FILE.sha256"
NAME=aav-restore-$$
docker run -d --rm --name "$NAME" -e POSTGRES_PASSWORD=rehearsal -e POSTGRES_DB=aav postgres:16-alpine >/dev/null
trap 'docker stop "$NAME" >/dev/null' EXIT
until docker exec "$NAME" pg_isready -U postgres >/dev/null 2>&1; do sleep 1; done
docker exec "$NAME" psql -U postgres -d aav -c "CREATE ROLE aav_app LOGIN; CREATE ROLE aav_owner LOGIN" >/dev/null
openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -pass "file:${AAV_BACKUP_PASSPHRASE_FILE:?}" -in "$FILE" \
  | docker exec -i "$NAME" pg_restore -U postgres -d aav --no-owner
docker exec "$NAME" psql -U postgres -d aav -tAc "SELECT 'tenants=' || count(*) FROM aav.tenants"
docker exec "$NAME" psql -U postgres -d aav -tAc "SELECT 'audit_rows=' || count(*) FROM aav.audit_log"
echo "restore rehearsal passed"
