#!/usr/bin/env bash
set -Eeuo pipefail
# Restores into a disposable, isolated PostgreSQL container; NEVER the staging database.
cd "$(dirname "$0")/../.."
umask 077
backup="${1:-}"
[[ -f "$backup" && ! -L "$backup" ]] || { echo "Usage: $0 /absolute/path/to/staging-backup.sql.gz" >&2; exit 2; }
backup="$(realpath "$backup")"
[[ "$backup" == /* && -f "$backup.sha256" ]] || { echo "Missing backup or checksum" >&2; exit 2; }
# Verify digest independently of the stored filename (supports absolute and relative manifests).
expected="$(awk 'NR==1 {print $1}' "$backup.sha256")"
[[ "$expected" =~ ^[0-9a-fA-F]{64}$ ]] || { echo "Invalid SHA256 manifest" >&2; exit 2; }
actual="$(sha256sum "$backup" | awk '{print $1}')"
[[ "${actual,,}" == "${expected,,}" ]] || { echo "Backup checksum mismatch" >&2; exit 2; }
gzip -t "$backup"
command -v docker >/dev/null
# Random, single-use name and credentials; no published ports or shared volumes.
id="$(python3 - <<'PY'
import secrets
print(secrets.token_hex(8))
PY
)"
name="aepx-restore-rehearsal-$id"
password="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
)"
cleanup() { docker rm -f "$name" >/dev/null 2>&1 || true; }
trap cleanup EXIT
docker run -d --name "$name" --network none --tmpfs /var/lib/postgresql/data:rw,size=512m \
  -e POSTGRES_USER=aepx -e POSTGRES_DB=aepx -e POSTGRES_PASSWORD="$password" \
  pgvector/pgvector:pg16 >/dev/null
ready=0
for _ in $(seq 1 40); do
  if docker exec "$name" pg_isready -U aepx -d aepx >/dev/null 2>&1; then ready=1; break; fi
  sleep 2
done
[[ "$ready" == 1 ]] || { echo "Disposable PostgreSQL did not become ready" >&2; exit 1; }
gzip -dc "$backup" | docker exec -i "$name" psql -X -v ON_ERROR_STOP=1 -U aepx -d aepx >/dev/null
docker exec "$name" psql -X -v ON_ERROR_STOP=1 -U aepx -d aepx -Atqc 'SELECT 1' | grep -qx 1
if [[ -n "${AEPX_RESTORE_EXPECT_AGENT_NAME:-}" ]]; then
  count="$(docker exec "$name" psql -X -v ON_ERROR_STOP=1 -v expected_name="$AEPX_RESTORE_EXPECT_AGENT_NAME" -U aepx -d aepx -Atc "SELECT count(*) FROM agents WHERE name = :'expected_name'")"
  [[ "$count" =~ ^[0-9]+$ && "$count" -ge 1 ]] || { echo "Expected agent missing after restore" >&2; exit 1; }
fi
echo "PASS: backup checksum, gzip, isolated restore and database query"
echo "This verifies logical restoration only; application-level recovery and off-host encryption remain separate gates."
