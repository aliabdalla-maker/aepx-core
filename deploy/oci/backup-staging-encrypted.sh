#!/usr/bin/env bash
set -Eeuo pipefail
# Encrypt the logical staging backup as it streams. No plaintext backup is written.
cd "$(dirname "$0")/../.."
umask 077
destination="${1:-}"
recipient="${AEPX_BACKUP_AGE_RECIPIENT:-}"
[[ "$destination" = /* && "$recipient" =~ ^age1[023456789acdefghjklmnpqrstuvwxyz]{58}$ ]] || {
  echo "Usage: AEPX_BACKUP_AGE_RECIPIENT=age1... $0 /absolute/private/backup/directory" >&2
  exit 2
}
command -v age >/dev/null || { echo "age CLI is required" >&2; exit 2; }
command -v docker >/dev/null || exit 2
python3 deploy/oci/validate-secrets.py >/dev/null
[[ ! -L "$destination" ]] || { echo "Symlink destination rejected" >&2; exit 2; }
parent="$(dirname "$destination")"
[[ -d "$parent" && ! -L "$parent" ]] || { echo "Backup parent must exist and must not be a symlink" >&2; exit 2; }
mkdir -p -- "$destination"
chmod 700 "$destination"
stamp="$(date -u +%Y%m%dT%H%M%SZ)-$(python3 -c 'import secrets;print(secrets.token_hex(4))')"
out="$destination/aepx-staging-$stamp.sql.gz.age"
[[ ! -e "$out" ]] || { echo "Backup name collision" >&2; exit 2; }
tmp="$out.partial"
trap 'rm -f -- "$tmp" "$out.sha256.partial"' EXIT
docker compose --env-file .env -p aepx-oci-staging -f deploy/oci/compose.staging.yml exec -T postgres \
  pg_dump -U aepx -d aepx --no-owner --no-acl | gzip -c | age -r "$recipient" -o "$tmp"
[[ -s "$tmp" ]] || { echo "Empty encrypted backup" >&2; exit 1; }
sha256sum "$tmp" | awk -v name="$(basename "$out")" '{print $1"  "name}' > "$out.sha256.partial"
chmod 600 "$tmp" "$out.sha256.partial"
mv -- "$tmp" "$out"
mv -- "$out.sha256.partial" "$out.sha256"
trap - EXIT
echo "Encrypted staging backup created: $out"
echo "NEXT: transfer to an access-controlled off-host location and verify decryption and restore."
