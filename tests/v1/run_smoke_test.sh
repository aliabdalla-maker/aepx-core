#!/usr/bin/env bash
# v1 test environment — automated smoke test.
#
# Brings up the minimal slice defined in docker-compose.test.yml, exercises
# the full protocol end-to-end including a real completion from the
# "machine learning box" (console -> connector bus -> trust -> policy ->
# aiplatform connector -> the main stack's already-warm Ollama), and tears
# itself down. Exits 0 on success, 1 on the first failed check, so it can
# be used as a CI gate (see ../../Jenkinsfile) or run by hand.
#
# Usage: bash tests/v1/run_smoke_test.sh [--keep]
#   --keep   leave the test environment running afterwards (for debugging)
set -uo pipefail
cd "$(dirname "$0")/../.."

# Prefer python3 (correct on the Linux-based Jenkins image this also runs
# under — see ../../Jenkinsfile) but fall back to python (Windows Git Bash
# dev boxes typically only have the latter). Getting this wrong doesn't
# error loudly — it silently makes every check below compare against an
# empty string and fail, which is exactly the bug this once shipped as.
PY=python3
command -v python3 >/dev/null 2>&1 || PY=python

COMPOSE="docker compose -p aepx-test -f docker-compose.test.yml"
KEEP=0
[ "${1:-}" = "--keep" ] && KEEP=1

PASS=0
FAIL=0

check() {
  local desc="$1" expect="$2" actual="$3"
  if [ "$actual" = "$expect" ]; then
    echo "  [PASS] $desc"
    PASS=$((PASS + 1))
  else
    echo "  [FAIL] $desc — expected '$expect', got '$actual'"
    FAIL=$((FAIL + 1))
  fi
}

cleanup() {
  if [ "$KEEP" -eq 0 ]; then
    echo "--- tearing down v1 test environment ---"
    $COMPOSE down -v --remove-orphans >/dev/null 2>&1
  else
    echo "--- --keep set: leaving v1 test environment running on ports 8100-8180 ---"
  fi
}
trap cleanup EXIT

echo "=== v1 smoke test: bringing up the isolated test environment ==="
$COMPOSE up -d --build
if [ $? -ne 0 ]; then
  echo "FATAL: docker compose up failed — see build output above"
  exit 1
fi

# Probe every port the checks below actually hit — not just a sample.
# This once probed only gateway/bus/console and relied, by accident, on the
# Ollama warm-up below taking ~90s to give trust/registry/governance time
# to finish booting; with the main stack (and its Ollama) down, that curl
# fails in ~1s and the checks fired against still-starting services.
echo "=== waiting for services to become reachable (up to 120s) ==="
READY_PORTS="8100 8102 8103 8109 8120 8180"
ready=0
for i in $(seq 1 40); do
  all_up=1
  for port in $READY_PORTS; do
    curl -sf --max-time 3 "http://localhost:$port/health" >/dev/null 2>&1 || { all_up=0; break; }
  done
  if [ "$all_up" -eq 1 ]; then
    ready=1
    break
  fi
  sleep 3
done
if [ "$ready" -ne 1 ]; then
  echo "FATAL: services did not become reachable within 120s"
  $COMPOSE ps
  exit 1
fi

# Ollama unloads the idle model on its own schedule (see docker-compose.yml
# OLLAMA_KEEP_ALIVE note); if nothing has queried it recently, the load can
# take up to ~88s — longer than the console/connector-bus 30s call budgets
# in the real request path. Force the load here, against Ollama directly
# with a timeout that can absorb a full cold start, so check 5 below always
# lands on an already-warm model instead of racing those budgets.
echo "=== warming the ML box (cold model load can take up to ~90s) ==="
curl -s --max-time 120 -X POST http://localhost:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.2:1b","prompt":"hi","stream":false}' >/dev/null 2>&1

echo "=== running checks ==="

# 1. Gateway aggregate health
status=$(curl -s --max-time 10 http://localhost:8100/health | "$PY" -c "import sys,json; d=json.load(sys.stdin); print('ok' if d.get('identity',{}).get('status')=='ok' else 'fail')" 2>/dev/null)
check "gateway aggregates identity health" "ok" "${status:-fail}"

# 2. Register an agent via the test Registry
agent_json=$(curl -s --max-time 10 -X POST http://localhost:8103/agents -H "Content-Type: application/json" -d '{"name":"v1-smoke-agent"}')
agent_id=$(echo "$agent_json" | "$PY" -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
check "agent registered with an id" "1" "$([ -n "$agent_id" ] && echo 1 || echo 0)"

# 3. Trust check — a fresh agent should get the default score
trust_score=$(curl -s --max-time 10 "http://localhost:8102/trust/$agent_id" | "$PY" -c "import sys,json; print(json.load(sys.stdin).get('trust_score',''))" 2>/dev/null)
check "trust score defaults to 50" "50" "${trust_score:-}"

# 4. Governance policy evaluation
allowed=$(curl -s --max-time 10 -X POST "http://localhost:8109/policy/evaluate?risk_level=AIA-R1" | "$PY" -c "import sys,json; print(json.load(sys.stdin).get('allowed',''))" 2>/dev/null)
check "policy allows a low-risk connector" "True" "${allowed:-}"

# 5. The centrepiece: a real completion from the machine-learning box,
#    through the full trust -> policy -> connector chain
chat_resp=$(curl -s --max-time 40 -X POST http://localhost:8180/api/chat -H "Content-Type: application/json" \
  -d '{"prompt":"Reply with exactly one word: online.","attachment_ids":[]}')
maturity=$(echo "$chat_resp" | "$PY" -c "import sys,json; print(json.load(sys.stdin).get('maturity',''))" 2>/dev/null)
check "console chat reaches the ML box (specialized or degraded, never absent)" "1" \
  "$([ "$maturity" = "specialized" ] || [ "$maturity" = "specialized_degraded" ] && echo 1 || echo 0)"

# 6. Bus denies a high-risk connector by policy (industrial connectors
#    aren't wired into the v1 slice, so this proves the deny path using
#    a connector the bus knows from the catalogue but has no live backend
#    for — the trust/policy gate must still fire before ever trying to
#    reach it)
deny_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 -X POST http://localhost:8120/bus/route \
  -H "Content-Type: application/json" \
  -d '{"sender":"aepx://agent/x","receiver":"aepx://connector/opcua","payload":{}}')
check "bus denies a policy-restricted connector" "403" "$deny_code"

echo ""
echo "=== v1 smoke test results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]
