#!/usr/bin/env bash
set -Eeuo pipefail
# Encrypt the logical staging backup as it streams. No plaintext backup is written.
cd "$(dirname "$0")/../.."
umask 077
destination="${1:-}"
recipient="${AEPX_BACKUP_AGE_RECIPIENT:-}"
[[ "$destination" = /* && -n "$recipient" ]] || {
  echo "Usage: AEPX_BACKUP_AGE_RECIPIENT=age1... $0 /absolute/private/backup/directory" >&2
  exit 2
}
command -v age >/dev/null || { echo "age CLI is required" >&2; exit 2; }
command -v docker >/dev/null || exit 2
python3 deploy/oci/validate-secrets.py >/dev/null
[[ ! -L "$destination" ]] || { echo "Symlink destination rejected" >&2; exit 2; }
mkdir -p -- "$destination"
chmod 700 "$destination"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
out="$destination/aepx-staging-$stamp.sql.gz.age"
[[ ! -e "$out" ]] || { echo "Backup name collision" >&2; exit 2; }
tmp="$out.partial"
trap 'rm -f -- "$tmp"' EXIT
docker compose --env-file .env -p aepx-oci-staging -f deploy/oci/compose.staging.yml exec -T postgres \
  pg_dump -U aepx -d aepx --no-owner --no-acl | gzip -c | age -r "$recipient" -o "$tmp"
[[ -s "$tmp" ]] || { echo "Empty encrypted backup" >&2; exit 1; }
mv -- "$tmp" "$out"
sha256sum "$out" > "$out.sha256"
chmod 600 "$out" "$out.sha256"
trap - EXIT
echo "Encrypted staging backup created: $out"
echo "NEXT: transfer to an access-controlled off-host location and verify decryption and restore."
