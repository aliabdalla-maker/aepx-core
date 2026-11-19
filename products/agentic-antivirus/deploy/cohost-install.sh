#!/usr/bin/env bash
# Installs or updates Agentic Antivirus beside an existing product on one VM (compose.cohost.yml).
# Run ON the VM from a checkout of aepx-core:  sudo -E products/agentic-antivirus/deploy/cohost-install.sh
# Env: AAV_PROXY_CONTAINER (default bam-caddy-1), AAV_SITE (default api.softwareequality.com).
# Safe to re-run. Every change to the shared reverse proxy is backed up, validated, and rolled back on failure.
set -euo pipefail
cd "$(dirname "$0")"
PROXY=${AAV_PROXY_CONTAINER:-bam-caddy-1}
SITE=${AAV_SITE:-api.softwareequality.com}
URL="https://$SITE/apps/agentic-antivirus"
say() { printf '\n== %s\n' "$*"; }

say "1/6 swap (avoids the kernel killing processes when memory is short)"
if [ "$(swapon --noheadings | wc -l)" = "0" ]; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo "2 GB swap added"
else echo "swap already present"; fi

say "2/6 secrets in /etc/aav (mode 600, never in git)"
install -d -m 700 /etc/aav
if [ ! -f /etc/aav/aav.env ]; then
  umask 077
  cat > /etc/aav/aav.env <<EOF
AAV_POSTGRES_PASSWORD=$(openssl rand -hex 24)
AAV_APP_DB_PASSWORD=$(openssl rand -hex 24)
AAV_SIGNING_KEY_PATH=/etc/aav/signing_key.pem
EOF
  echo "generated /etc/aav/aav.env"
else echo "keeping existing /etc/aav/aav.env"; fi
if [ ! -f /etc/aav/signing_key.pem ]; then
  openssl genpkey -algorithm ed25519 -out /etc/aav/signing_key.pem
  echo "generated Ed25519 signing key"
fi
chown 10001 /etc/aav/signing_key.pem && chmod 400 /etc/aav/signing_key.pem
set -a; . /etc/aav/aav.env; set +a

say "3/6 reverse proxy network"
docker inspect "$PROXY" >/dev/null || { echo "proxy container $PROXY not found" >&2; exit 1; }
AAV_PROXY_NETWORK=$(docker inspect "$PROXY" -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' | awk '{print $1}')
export AAV_PROXY_NETWORK
echo "proxy $PROXY on network $AAV_PROXY_NETWORK"

say "4/6 build and start (memory capped at about 1.1 GB in total)"
python3 guard.py >/dev/null 2>&1 || echo "note: guard.py needs docker compose; continuing with explicit caps from compose.cohost.yml"
docker compose -f compose.yml -f compose.cohost.yml up -d --build
for i in $(seq 1 60); do
  docker compose -f compose.yml -f compose.cohost.yml exec -T web wget -qO- http://127.0.0.1:8080/api/ready 2>/dev/null | grep -q '"ready":true' && break
  sleep 5
done
docker compose -f compose.yml -f compose.cohost.yml exec -T web wget -qO- http://127.0.0.1:8080/api/ready | grep -q '"ready":true' \
  || { echo "control plane did not become ready; proxy left unchanged" >&2; docker compose -f compose.yml -f compose.cohost.yml logs --tail 40 control-plane >&2; exit 1; }
echo "stack ready"
# Ship the baseline detection rules if nothing is published yet, so newly enrolled devices can scan.
docker compose -f compose.yml -f compose.cohost.yml exec -T control-plane python -m app.admin publish-baseline || true

say "5/6 route $URL/ through $PROXY (backup, validate, roll back on failure)"
CF_HOST=$(docker inspect "$PROXY" -f '{{range .Mounts}}{{if eq .Destination "/etc/caddy/Caddyfile"}}{{.Source}}{{end}}{{end}}')
[ -n "$CF_HOST" ] && [ -f "$CF_HOST" ] || { echo "cannot find the Caddyfile mounted into $PROXY" >&2; exit 1; }
if grep -q 'handle_path /apps/agentic-antivirus/\*' "$CF_HOST"; then
  echo "route already present in $CF_HOST"
else
  BK="$CF_HOST.bak-$(date +%Y%m%d-%H%M%S)"; cp -p "$CF_HOST" "$BK"; echo "backup: $BK"
  python3 - "$CF_HOST" "$SITE" caddy-cohost.caddy <<'PY'
import re, sys
path, site, snip = sys.argv[1], sys.argv[2], open(sys.argv[3]).read()
lines = open(path).read().split("\n")
body = "\n".join("\t" + l if l.strip() else l for l in snip.split("\n") if not l.startswith("#"))
for i, l in enumerate(lines):
    names = re.split(r"[,\s]+", l.strip().rstrip("{").strip())
    if l.rstrip().endswith("{") and site in names:
        lines.insert(i + 1, body.rstrip("\n"))
        open(path, "w").write("\n".join(lines))
        sys.exit(0)
sys.exit(f"site block for {site} not found")
PY
  if docker exec "$PROXY" caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1 \
     && docker exec "$PROXY" caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile; then
    echo "route added and proxy reloaded"
  else
    cp -p "$BK" "$CF_HOST"; docker exec "$PROXY" caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile || true
    echo "proxy rejected the change; original Caddyfile restored" >&2; exit 1
  fi
fi

say "6/6 public checks"
sleep 2
curl -fsS "$URL/api/ready" && echo
curl -fsS -o /dev/null -w "console login page: HTTP %{http_code}\n" "$URL/login/"
git -C ../../.. rev-parse HEAD > .last-verified-sha
echo "deployed $(cat .last-verified-sha) at $URL/"
