#!/usr/bin/env bash
set -Eeuo pipefail
# Staging-only logical backup. Keep backup output off-host and encrypted.
cd "$(dirname "$0")/../.."
umask 077
[[ -f .env ]] || { echo "Missing private .env" >&2; exit 1; }
python3 deploy/oci/validate-secrets.py >/dev/null
command -v docker >/dev/null
destination="${1:-}"
[[ -n "$destination" && "$destination" = /* ]] || { echo "Usage: $0 /absolute/path/to/private-backup-directory" >&2; exit 2; }
mkdir -p -- "$destination"
[[ -d "$destination" && ! -L "$destination" ]] || { echo "Backup destination invalid" >&2; exit 2; }
chmod 700 "$destination"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
out="$destination/aepx-staging-$stamp.sql.gz"
tmp="$out.partial"
trap 'rm -f -- "$tmp"' EXIT
docker compose --env-file .env -p aepx-oci-staging -f deploy/oci/compose.staging.yml exec -T postgres pg_dump -U aepx -d aepx --no-owner --no-acl | gzip -c > "$tmp"
[[ -s "$tmp" ]] && gzip -t "$tmp"
mv -- "$tmp" "$out"
sha256sum "$out" > "$out.sha256"
chmod 600 "$out" "$out.sha256"
trap - EXIT
echo "Staging backup created: $out"
echo "IMPORTANT: Copy encrypted off-host and test restoration separately; this script does not verify restore."
