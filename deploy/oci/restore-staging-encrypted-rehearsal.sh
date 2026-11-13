#!/usr/bin/env bash
set -Eeuo pipefail
# Decrypt only into a private temporary directory and restore into disposable PostgreSQL.
cd "$(dirname "$0")/../.."
umask 077
encrypted="${1:-}"
identity="${AEPX_BACKUP_AGE_IDENTITY:-}"
[[ "$encrypted" = /* && "$identity" = /* && -f "$encrypted" && ! -L "$encrypted" && -f "$encrypted.sha256" && ! -L "$encrypted.sha256" && -f "$identity" && ! -L "$identity" ]] || {
  echo "Usage: AEPX_BACKUP_AGE_IDENTITY=/private/identity.txt $0 /absolute/backup.sql.gz.age" >&2
  exit 2
}
command -v age >/dev/null
[[ ! -L "$encrypted.sha256" ]] || exit 2
identity_mode="$(stat -c %a "$identity")"
[[ $(( 8#$identity_mode & 077 )) -eq 0 ]] || { echo "Private age identity must be mode 600 or stricter" >&2; exit 2; }
expected="$(awk 'NR==1{print $1}' "$encrypted.sha256")"
[[ "$expected" =~ ^[0-9a-fA-F]{64}$ ]] || exit 2
actual="$(sha256sum "$encrypted" | awk '{print $1}')"
[[ "${actual,,}" == "${expected,,}" ]] || { echo "Encrypted backup checksum mismatch" >&2; exit 2; }
[[ ! -L "$(dirname "$encrypted")" ]] || { echo "Symlinked backup parent rejected" >&2; exit 2; }
tmpdir="$(mktemp -d)"
chmod 700 "$tmpdir"
trap 'rm -rf -- "$tmpdir"' EXIT
age -d -i "$identity" -o "$tmpdir/restore.sql.gz" "$encrypted"
gzip -t "$tmpdir/restore.sql.gz"
sha256sum "$tmpdir/restore.sql.gz" > "$tmpdir/restore.sql.gz.sha256"
bash deploy/oci/restore-staging-rehearsal.sh "$tmpdir/restore.sql.gz"
echo "PASS: encrypted backup decrypted and restored in disposable isolated database"
