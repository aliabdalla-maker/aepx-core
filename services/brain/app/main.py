"""AEP-X Brain — the platform's self-learning, self-healing monitor.

Two jobs, deliberately kept separate from Trust (which learns about
*agents* from their behaviour):

1. Self-healing: watches every core service's /health, re-warms a cold
   Ollama before users hit the timeout, and runs a circuit breaker per
   connector so a connector having a bad day gets a fast, honest denial
   instead of every caller re-discovering the same 30s timeout.
2. Self-learning: derives each connector's reliability score from the
   Governance Engine's real audit history (not synthetic data) and
   persists circuit-breaker state so what it has learned survives a
   restart — a "self-learning" system that forgets everything on reboot
   isn't really learning.

Every state transition is published to Kafka (brain.* topics) so the
Governance Engine's unconditional audit consumer captures every
self-healing action automatically (Law 8) — the brain does not get to
act silently.
"""
import json
import os
import threading
import time

import httpx
from fastapi import FastAPI

app = FastAPI(title="AEP-X Brain", version="0.1.0")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://aepx:aepx_dev_only@postgres:5432/aepx")
GOVERNANCE_URL = os.getenv("GOVERNANCE_URL", "http://governance:8000")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
POLL_INTERVAL = float(os.getenv("BRAIN_POLL_INTERVAL", "20"))

# name -> health URL. Kept as a flat dict (not the catalogue) since these
# are the platform's own services, not external connectors.
MONITORED_SERVICES = {
    "identity": "http://identity:8000/health", "trust": "http://trust:8000/health",
    "registry": "http://registry:8000/health", "memory": "http://memory:8000/health",
    "cache": "http://cache:8000/health", "gateway": "http://gateway:8000/health",
    "discovery": "http://discovery:8000/health", "workflow": "http://workflow:8000/health",
    "safety": "http://safety:8000/health", "governance": "http://governance:8000/health",
    "knowledge": "http://knowledge:8000/health", "verification": "http://verification:8000/health",
    "cost-optimiser": "http://cost-optimiser:8000/health", "ml-integration": "http://ml-integration:8000/health",
    "connector-bus": "http://connector-bus:8000/health", "console": "http://console:8000/health",
}

CIRCUIT_FAILURE_THRESHOLD = 5   # consecutive connector.failed before opening
CIRCUIT_COOLDOWN_SECONDS = 60   # how long OPEN holds before a HALF_OPEN trial
DOWN_THRESHOLD = 3              # consecutive failed health checks before "down"

try:
    import psycopg
    _PG_AVAILABLE = True
except Exception:
    _PG_AVAILABLE = False

try:
    from kafka import KafkaProducer
    _KAFKA_IMPORTABLE = True
except Exception:
    _KAFKA_IMPORTABLE = False

_producer = None
_service_state: dict[str, dict] = {name: {"up": True, "consecutive_failures": 0} for name in MONITORED_SERVICES}
_circuit_fallback: dict[str, dict] = {}
_incidents_fallback: list[dict] = []
_lock = threading.Lock()


def _get_conn():
    if not _PG_AVAILABLE:
        return None
    try:
        return psycopg.connect(DATABASE_URL, connect_timeout=3)
    except Exception:
        return None


def _get_producer():
    global _producer
    if _producer is None and _KAFKA_IMPORTABLE:
        try:
            _producer = KafkaProducer(
                bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP", "kafka:9092"),
                value_serializer=lambda v: json.dumps(v).encode(),
            )
        except Exception:
            _producer = None
    return _producer


def _record_incident(kind: str, target: str, detail: str = ""):
    conn = _get_conn()
    if conn:
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO brain.incidents (kind, target, detail) VALUES (%s, %s, %s)",
                    (kind, target, detail),
                )
            conn.close()
        except Exception:
            conn.close()
            _incidents_fallback.append({"kind": kind, "target": target, "detail": detail, "created_at": time.time()})
    else:
        _incidents_fallback.append({"kind": kind, "target": target, "detail": detail, "created_at": time.time()})

    producer = _get_producer()
    if producer:
        producer.send(f"brain.{kind}", {"target": target, "detail": detail, "ts": time.time()})


def _load_circuit(connector: str) -> dict:
    conn = _get_conn()
    if conn:
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT state, consecutive_failures, reliability_score, opened_at FROM brain.circuit_state "
                    "WHERE connector = %s",
                    (connector,),
                )
                row = cur.fetchone()
            conn.close()
            if row:
                return {"state": row[0], "consecutive_failures": row[1], "reliability_score": float(row[2]),
                        "opened_at": row[3].timestamp() if row[3] else None}
            return {"state": "closed", "consecutive_failures": 0, "reliability_score": 1.0, "opened_at": None}
        except Exception:
            conn.close()
    return _circuit_fallback.get(connector, {"state": "closed", "consecutive_failures": 0,
                                              "reliability_score": 1.0, "opened_at": None})


def _save_circuit(connector: str, data: dict):
    conn = _get_conn()
    if conn:
        try:
            opened_at_sql = "to_timestamp(%s)" if data["opened_at"] else "NULL"
            params = [connector, data["state"], data["consecutive_failures"], data["reliability_score"]]
            if data["opened_at"]:
                params.append(data["opened_at"])
            with conn, conn.cursor() as cur:
                cur.execute(
                    f"""INSERT INTO brain.circuit_state (connector, state, consecutive_failures, reliability_score, opened_at)
                        VALUES (%s, %s, %s, %s, {opened_at_sql})
                        ON CONFLICT (connector) DO UPDATE SET
                            state = EXCLUDED.state, consecutive_failures = EXCLUDED.consecutive_failures,
                            reliability_score = EXCLUDED.reliability_score, opened_at = EXCLUDED.opened_at,
                            updated_at = now()""",
                    params,
                )
            conn.close()
            return
        except Exception:
            conn.close()
    _circuit_fallback[connector] = data


def _recompute_reliability_and_circuits():
    """Self-learning step: derive each connector's reliability from the
    Governance Engine's real audit trail, and drive the circuit breaker
    state machine from it — CLOSED -> OPEN on a failure streak, OPEN ->
    HALF_OPEN after a cooldown, HALF_OPEN -> CLOSED/OPEN on the next result."""
    try:
        resp = httpx.get(f"{GOVERNANCE_URL}/audit", params={"limit": 300}, timeout=5.0)
        events = resp.json()
    except Exception:
        return

    per_connector: dict[str, list[bool]] = {}
    for item in events:
        if not item["topic"].startswith("connector."):
            continue
        ev = item["event"]
        name = ev.get("connector")
        if not name:
            continue
        per_connector.setdefault(name, []).append(ev.get("outcome") == "invoked")

    now = time.time()
    with _lock:
        for name, outcomes in per_connector.items():
            reliability = sum(outcomes) / len(outcomes) if outcomes else 1.0
            # consecutive failures at the *front* of history (most recent first,
            # since Governance returns newest-first)
            consecutive_failures = 0
            for ok in outcomes:
                if ok:
                    break
                consecutive_failures += 1

            circuit = _load_circuit(name)
            prev_state = circuit["state"]
            new_state = prev_state

            if prev_state == "closed" and consecutive_failures >= CIRCUIT_FAILURE_THRESHOLD:
                new_state = "open"
                circuit["opened_at"] = now
            elif prev_state == "open" and circuit["opened_at"] and now - circuit["opened_at"] >= CIRCUIT_COOLDOWN_SECONDS:
                new_state = "half_open"
            elif prev_state == "half_open":
                # the most recent event is the trial result
                if outcomes and outcomes[0]:
                    new_state = "closed"
                    circuit["opened_at"] = None
                elif consecutive_failures >= 1:
                    new_state = "open"
                    circuit["opened_at"] = now

            circuit["state"] = new_state
            circuit["consecutive_failures"] = consecutive_failures
            circuit["reliability_score"] = round(reliability, 3)
            _save_circuit(name, circuit)

            if new_state != prev_state:
                kind = {"open": "circuit_opened", "closed": "circuit_closed", "half_open": "circuit_half_open"}[new_state]
                _record_incident(kind, name, f"reliability={circuit['reliability_score']}, consecutive_failures={consecutive_failures}")


def _check_ollama():
    try:
        httpx.get(f"{OLLAMA_URL}/api/tags", timeout=3.0)
    except Exception:
        try:
            httpx.post(f"{OLLAMA_URL}/api/generate", json={"model": OLLAMA_MODEL, "prompt": "hi", "stream": False}, timeout=45.0)
            _record_incident("ollama_rewarmed", "ollama", f"model={OLLAMA_MODEL}")
        except Exception:
            pass  # Ollama itself may be down — the aiplatform connector's own fallback covers callers


def _check_services():
    for name, url in MONITORED_SERVICES.items():
        state = _service_state[name]
        try:
            resp = httpx.get(url, timeout=3.0)
            ok = resp.status_code == 200
        except Exception:
            ok = False

        if ok:
            if not state["up"] and state["consecutive_failures"] >= DOWN_THRESHOLD:
                _record_incident("service_recovered", name)
            state["up"] = True
            state["consecutive_failures"] = 0
        else:
            state["consecutive_failures"] += 1
            if state["up"] and state["consecutive_failures"] >= DOWN_THRESHOLD:
                state["up"] = False
                _record_incident("service_down", name, f"{DOWN_THRESHOLD} consecutive failed health checks")


def _monitor_loop():
    while True:
        try:
            _check_services()
            _check_ollama()
            _recompute_reliability_and_circuits()
        except Exception:
            pass
        time.sleep(POLL_INTERVAL)


@app.get("/health")
def health():
    conn = _get_conn()
    persisted = conn is not None
    if conn:
        conn.close()
    return {"status": "ok", "service": "brain", "persisted": persisted, "monitoring": len(MONITORED_SERVICES)}


@app.get("/brain/status")
def brain_status():
    return {
        "services": {name: {"up": s["up"], "consecutive_failures": s["consecutive_failures"]}
                     for name, s in _service_state.items()},
    }


@app.get("/brain/circuit/{connector}")
def circuit_status(connector: str):
    # The Connector Bus consults this before invoking — fail-open by design
    # (see connector-bus's BRAIN_URL integration): if the Brain itself is
    # unreachable, the bus must never let that block a normal call.
    c = _load_circuit(connector)
    return {"connector": connector, "allowed": c["state"] != "open", **c}


@app.get("/brain/reliability")
def reliability():
    conn = _get_conn()
    if conn:
        try:
            with conn, conn.cursor() as cur:
                cur.execute("SELECT connector, reliability_score, state FROM brain.circuit_state ORDER BY reliability_score ASC")
                rows = cur.fetchall()
            conn.close()
            return [{"connector": r[0], "reliability_score": float(r[1]), "state": r[2]} for r in rows]
        except Exception:
            conn.close()
    return [{"connector": k, "reliability_score": v["reliability_score"], "state": v["state"]}
            for k, v in _circuit_fallback.items()]


@app.get("/brain/incidents")
def incidents(limit: int = 100):
    conn = _get_conn()
    if conn:
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT kind, target, detail, created_at FROM brain.incidents ORDER BY created_at DESC LIMIT %s",
                    (limit,),
                )
                rows = cur.fetchall()
            conn.close()
            return [{"kind": r[0], "target": r[1], "detail": r[2], "created_at": r[3].timestamp()} for r in rows]
        except Exception:
            conn.close()
    return list(reversed(_incidents_fallback))[:limit]


threading.Thread(target=_monitor_loop, daemon=True).start()
