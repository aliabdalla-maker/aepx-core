from fastapi import FastAPI
import json
import os
import threading
import time

app = FastAPI(title="AEP-X Governance Engine", version="0.2.0")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://aepx:aepx_dev_only@postgres:5432/aepx")
_RISK_ORDER = ["S0", "S1", "S2", "S3", "S4"]
_POLICIES = {"max_risk_level": "S2"}  # seed policy — extend via RFC-0006 categories

try:
    from kafka import KafkaConsumer
    _KAFKA_AVAILABLE = True
except Exception:
    _KAFKA_AVAILABLE = False

try:
    import psycopg
    _PG_AVAILABLE = True
except Exception:
    _PG_AVAILABLE = False

# Fallback so audit recording never crashes the consumer thread even if
# Postgres is briefly unreachable — state just won't survive a restart then.
_AUDIT_FALLBACK: list[dict] = []


def _get_conn():
    if not _PG_AVAILABLE:
        return None
    try:
        return psycopg.connect(DATABASE_URL, connect_timeout=3)
    except Exception:
        return None


@app.get("/health")
def health():
    conn = _get_conn()
    persisted = conn is not None
    if conn:
        conn.close()
    return {"status": "ok", "service": "governance", "persisted": persisted}


@app.post("/policy/evaluate")
def evaluate_policy(risk_level: str):
    # AIA-R and Safety S-class both use a 5-level 0-4 scale (see
    # SOA-Architecture.md §1.1 for why they're kept as two distinct,
    # 1:1-mapped taxonomies rather than merged). This endpoint accepts
    # either an "S0"-"S4" or "AIA-R0"-"AIA-R4" style label and maps it to
    # the same ordinal check against the seed policy.
    level = risk_level.replace("AIA-R", "S") if risk_level.startswith("AIA-R") else risk_level
    try:
        requested_idx = _RISK_ORDER.index(level)
        max_idx = _RISK_ORDER.index(_POLICIES["max_risk_level"])
    except ValueError:
        return {"risk_level": risk_level, "allowed": False, "reason": "unrecognised risk level"}
    allowed = requested_idx <= max_idx
    return {"risk_level": risk_level, "allowed": allowed, "max_risk_level": _POLICIES["max_risk_level"]}


@app.get("/audit")
def get_audit(limit: int = 200):
    conn = _get_conn()
    if conn:
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT topic, event, recorded_at FROM governance.audit_log "
                    "ORDER BY recorded_at DESC LIMIT %s",
                    (limit,),
                )
                rows = cur.fetchall()
            return [{"topic": r[0], "event": r[1], "recorded_at": r[2].timestamp()} for r in rows]
        except Exception:
            pass
        finally:
            conn.close()

    return list(reversed(_AUDIT_FALLBACK))[:limit]


def _record(topic: str, event: dict):
    conn = _get_conn()
    if conn:
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO governance.audit_log (topic, event) VALUES (%s, %s)",
                    (topic, json.dumps(event)),
                )
            return
        except Exception:
            pass
        finally:
            conn.close()
    _AUDIT_FALLBACK.append({"topic": topic, "event": event, "recorded_at": time.time()})


def consume_all_events():
    # Two jobs, per Microservices-Implementation-Guide.html §5.4: evaluate
    # policy on demand (above), and consume every topic unconditionally to
    # build the audit trail — this is the one service allowed to know
    # about all events, which is what makes 100% audit coverage achievable
    # without instrumenting every other service.
    #
    # The reconnect loop is load-bearing: the broker usually isn't ready
    # when this thread starts (compose startup race), and a consumer thread
    # that dies silently means 0% audit coverage while /health still says ok.
    if not _KAFKA_AVAILABLE:
        return
    topics = ["workflow.completed", "safety.flagged", "verification.completed",
              "connector.invoked", "connector.failed", "trust.updated"]
    while True:
        try:
            consumer = KafkaConsumer(*topics, bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP", "kafka:9092"),
                                      auto_offset_reset="earliest",
                                      value_deserializer=lambda v: json.loads(v.decode()))
            for msg in consumer:
                _record(msg.topic, msg.value)
        except Exception:
            time.sleep(5)


threading.Thread(target=consume_all_events, daemon=True).start()
