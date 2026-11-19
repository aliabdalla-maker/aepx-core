#!/usr/bin/env bash
# Runs ON the OCI VM, invoked only by the approval-gated deploy-production job (or manually by the release
# owner). Order: preflight guard -> encrypted backup -> build/start -> readiness + smoke -> on failure roll back
# to the previous verified SHA (CI-14, CI-15, OCI-13, RA-11, RA-12).
set -euo pipefail
SHA=${1:?usage: deploy.sh VERIFIED_SHA}
cd "$(dirname "$0")"
test "$(git rev-parse HEAD)" = "$SHA" || { echo "checkout is not $SHA" >&2; exit 1; }
PREV=$(cat .last-verified-sha 2>/dev/null || true)
set -a; . /etc/aav/aav.env; set +a        # secrets live on the host (mode 600), never in git
python3 guard.py >/dev/null
export AAV_BUILD_SHA=${SHA:0:12}
./backup.sh
docker compose up -d --build
for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:18480/api/ready >/dev/null; then break; fi
  sleep 5
done
if curl -fsS http://127.0.0.1:18480/api/ready | grep -q '"ready":true' && curl -fsS http://127.0.0.1:18480/login/ >/dev/null; then
  echo "$SHA" > .last-verified-sha
  curl -fsS http://127.0.0.1:18480/api/health
  echo "deployed $SHA"
else
  echo "readiness failed; rolling back to ${PREV:-nothing}" >&2
  if [ -n "$PREV" ]; then git -C ../../.. checkout "$PREV" && docker compose up -d --build; fi
  exit 1
fi
