#!/usr/bin/env bash
# Rollback rehearsal (CI-15, OCI-12, RA-12). Rolls TARGET back from CURRENT_SHA to PREVIOUS_SHA exactly as a failed
# release would be rolled back, proves the previous build is serving, then rolls forward again. While it runs, a
# sampler probes /api/ready once a second, so the evidence shows how many seconds the service was unavailable.
#   rollback-rehearsal.sh CURRENT_SHA PREVIOUS_SHA [staging|production]
# Run ON the VM from the aepx-core checkout, staging first. The current deploy tooling is used for both legs
# (copied to a temp dir), so older releases without the newer scripts still roll back the same way.
# Evidence: $AAV_EVIDENCE_DIR/rollback-<target>-<UTC>.json (default /var/lib/aav/evidence).
set -euo pipefail
CUR=${1:?usage: rollback-rehearsal.sh CURRENT_SHA PREVIOUS_SHA [staging|production]}
PREV=${2:?usage: rollback-rehearsal.sh CURRENT_SHA PREVIOUS_SHA [staging|production]}
TARGET=${3:-staging}
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(git -C "$HERE" rev-parse --show-toplevel)
EVID=${AAV_EVIDENCE_DIR:-/var/lib/aav/evidence}; mkdir -p "$EVID"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
KIT=$(mktemp -d); trap 'kill "$SAMPLER" 2>/dev/null || true; rm -rf "$KIT"' EXIT
cp "$HERE"/{deploy.sh,backup.sh,migrate.sh,guard.py,compose.staging.yml} "$KIT"/
if [ "$TARGET" = staging ]; then
  export COMPOSE_PROJECT_NAME=agentic-antivirus-staging COMPOSE_FILE="compose.yml:$KIT/compose.staging.yml"
else
  set -a; . "${AAV_ENV_FILE:-/etc/aav/aav.env}"; set +a
  export COMPOSE_PROJECT_NAME=agentic-antivirus COMPOSE_FILE=${AAV_COMPOSE_FILES:-compose.yml}
fi
PROBES="$KIT/probes"
( cd "$HERE"; while :; do
    if docker compose exec -T web wget -qO- http://127.0.0.1:8080/api/ready 2>/dev/null | grep -q '"ready":true'
    then echo "$(date +%s) up"; else echo "$(date +%s) down"; fi >> "$PROBES"; sleep 1
  done ) & SAMPLER=$!

leg() {  # leg SHA -> deploy SHA with the current tooling, print seconds taken
  local sha=$1 t0; t0=$(date +%s)
  git -C "$REPO" checkout -q "$sha"
  AAV_DEPLOY_DIR="$REPO/products/agentic-antivirus/deploy" AAV_SKIP_STAGING=1 "$KIT/deploy.sh" "$sha" "$TARGET" >&2
  echo $(( $(date +%s) - t0 ))
}
health_build() { (cd "$HERE" && docker compose exec -T web wget -qO- http://127.0.0.1:8080/api/health 2>/dev/null) \
  | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("build",""))
except Exception: print("")'; }

T_BACK=$(leg "$PREV"); B_BACK=$(health_build)
T_FWD=$(leg "$CUR"); B_FWD=$(health_build)
sleep 2; kill "$SAMPLER" 2>/dev/null || true
DOWN=$(grep -c ' down$' "$PROBES" || true); TOTAL=$(wc -l < "$PROBES")
OK=false; case "$B_BACK" in "${PREV:0:12}"*|"${PREV:0:7}"*) case "$B_FWD" in "${CUR:0:12}"*) OK=true;; esac;; esac
# 0.1.1 and older do not report "build" in /health: then the leg's deploy.sh success is the proof.
[ -z "$B_BACK" ] && case "$B_FWD" in "${CUR:0:12}"*) OK=true;; esac
OUT="$EVID/rollback-$TARGET-$STAMP.json"
cat > "$OUT" <<JSON
{"rehearsal": "rollback", "target": "$TARGET", "at": "$STAMP", "current": "$CUR", "previous": "$PREV",
 "rollback_seconds": $T_BACK, "rollforward_seconds": $T_FWD, "build_after_rollback": "$B_BACK",
 "build_after_rollforward": "$B_FWD", "probes": $TOTAL, "unavailable_seconds": $DOWN, "passed": $OK}
JSON
cat "$OUT"
$OK && echo "rollback rehearsal passed" || { echo "rollback rehearsal FAILED" >&2; exit 1; }
