#!/usr/bin/env bash
# Runs ON the OCI VM, invoked by the approval-gated deploy jobs (or manually by the release owner).
#   deploy.sh VERIFIED_SHA [production|staging]
# Order: staging gate (production only) -> preflight guard -> encrypted backup -> migrate -> build/start ->
# readiness + smoke -> record; on failure roll back to the previous verified SHA (CI-14, CI-15, OCI-13, RA-11,
# RA-12, OCI-16). Works with the plain stack (compose.yml) and the shared-VM layout (AAV_COMPOSE_FILES=
# compose.yml:compose.cohost.yml in /etc/aav/aav.env): readiness is checked inside the web container, so no
# published port is needed.
set -euo pipefail
SHA=${1:?usage: deploy.sh VERIFIED_SHA [production|staging]}
TARGET=${2:-production}
# TOOLS = where these scripts live; the compose files come from AAV_DEPLOY_DIR (default: the same directory).
# rollback-rehearsal.sh runs the current tooling against an older checkout this way.
TOOLS=$(cd "$(dirname "$0")" && pwd)
cd "${AAV_DEPLOY_DIR:-$TOOLS}"
DEPLOY_DIR=$(pwd)
export AAV_COMPOSE_DIR=$DEPLOY_DIR
log() { printf '%s [%s] %s\n' "$(date -u +%H:%M:%S)" "$TARGET" "$*"; }
test "$(git rev-parse HEAD)" = "$SHA" || { echo "checkout is not $SHA" >&2; exit 1; }

case "$TARGET" in
  production)
    ENV_FILE=${AAV_ENV_FILE:-/etc/aav/aav.env}; PROJECT=agentic-antivirus; MARK=.last-verified-sha ;;
  staging)
    ENV_FILE=${AAV_ENV_FILE:-/etc/aav/aav-staging.env}; PROJECT=agentic-antivirus-staging; MARK=.last-verified-sha-staging ;;
  *) echo "unknown target $TARGET (production|staging)" >&2; exit 2 ;;
esac
set -a; . "$ENV_FILE"; set +a        # secrets live on the host (mode 600), never in git

# Staging gate: production only takes a commit that passed staging, unless the release owner overrides it.
if [ "$TARGET" = production ] && ! grep -qx "$SHA" .staged-shas 2>/dev/null; then
  if [ "${AAV_SKIP_STAGING:-}" = "1" ]; then
    log "WARNING: $SHA was not verified in staging; AAV_SKIP_STAGING=1 override recorded"
    echo "$(date -u +%FT%TZ) $SHA skip-staging" >> .staging-overrides
  else
    echo "$SHA has not passed staging: run 'deploy.sh $SHA staging' first (or set AAV_SKIP_STAGING=1)" >&2; exit 3
  fi
fi

export COMPOSE_PROJECT_NAME=$PROJECT
if [ "$TARGET" = staging ]; then
  OVERLAY=compose.staging.yml; [ -f "$OVERLAY" ] || OVERLAY=$TOOLS/compose.staging.yml   # older checkouts
  export COMPOSE_FILE=compose.yml:$OVERLAY
  export AAV_BACKUP_DIR=${AAV_BACKUP_DIR:-/var/backups/aav-staging}
else
  export COMPOSE_FILE=${AAV_COMPOSE_FILES:-compose.yml}
fi
export AAV_BUILD_SHA=${SHA:0:12} AAV_ENVIRONMENT=$TARGET
PREV=$(cat "$MARK" 2>/dev/null || true)
DC="docker compose"

python3 "$TOOLS/guard.py" >/dev/null
log "guard passed ($COMPOSE_FILE)"

ready() { $DC exec -T web wget -qO- http://127.0.0.1:8080/api/ready 2>/dev/null | grep -q '"ready":true'; }
smoke() { ready && $DC exec -T web wget -qO- http://127.0.0.1:8080/login/ >/dev/null 2>&1 \
  && $DC exec -T web wget -qO- http://127.0.0.1:8080/api/health 2>/dev/null | grep -q "\"build\":\"$AAV_BUILD_SHA"; }

$DC up -d postgres
for _ in $(seq 1 30); do $DC exec -T postgres pg_isready -U aav_owner -d aav >/dev/null 2>&1 && break; sleep 2; done
if [ -n "${AAV_BACKUP_PASSPHRASE_FILE:-}" ]; then
  "$TOOLS/backup.sh"
elif [ "$TARGET" = production ]; then
  echo "AAV_BACKUP_PASSPHRASE_FILE not set: production never deploys without a backup" >&2; exit 4
fi
$DC exec -T postgres sh -s < "$TOOLS/migrate.sh"
$DC up -d --build
for _ in $(seq 1 "${AAV_READY_TRIES:-60}"); do ready && break; sleep "${AAV_READY_SLEEP:-5}"; done
$DC exec -T control-plane python -m app.admin publish-baseline >/dev/null 2>&1 || true

if smoke; then
  echo "$SHA" > "$MARK"
  [ "$TARGET" = staging ] && { grep -qx "$SHA" .staged-shas 2>/dev/null || echo "$SHA" >> .staged-shas; }
  $DC exec -T web wget -qO- http://127.0.0.1:8080/api/health; echo
  log "deployed $SHA"
else
  log "readiness/smoke failed; rolling back to ${PREV:-nothing}" >&2
  $DC logs --tail 40 control-plane >&2 || true
  if [ -n "$PREV" ]; then
    git -C ../../.. checkout -q "$PREV"
    (cd "$DEPLOY_DIR" && AAV_BUILD_SHA=${PREV:0:12} $DC up -d --build)
    log "rolled back to $PREV"
  fi
  exit 1
fi
