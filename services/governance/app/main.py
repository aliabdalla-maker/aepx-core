from fastapi import FastAPI
import json
import os
import threading
import time

from app import ledger

app = FastAPI(title="AEP-X Governance Engine", version="0.2.0")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://aepx:aepx_dev_only@postgres:5432/aepx")
_RISK_ORDER = ["S0", "S1", "S2", "S3", "S4"]
_POLICIES = {"max_risk_level": "S2"}  # seed policy — extend via RFC-0006 categories

_ANCHOR_BATCH_SIZE = 20
_LOCAL_ANCHOR = ledger.LocalHashChainAnchor()
_EVM_ANCHOR = ledger.EVMAnchorClient()

# Every topic this consumer subscribes to — KafkaConsumer matches exact
# topic names, not patterns, so a producer adding a new brain.* kind (see
# services/brain's _record_incident) must be mirrored here explicitly or
# its events are silently dropped from the audit trail. Kept as a
# module-level constant specifically so tests can catch that drift.
_CONSUMED_TOPICS = [
    "workflow.completed", "safety.flagged", "verification.completed",
    "connector.invoked", "connector.failed", "trust.updated",
    "brain.service_down", "brain.service_recovered", "brain.ollama_rewarmed",
    "brain.circuit_opened", "brain.circuit_closed", "brain.circuit_half_open",
    # RFC-0008 chain->AI oracle bridge (services/oracle-bridge): an on-chain
    # request for an AI decision, and the scored answer written back. Audited
    # here so every AI-for-a-contract call lands in the trail (Law 8).
    "oracle.requested", "oracle.fulfilled",
]

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
_LEDGER_FALLBACK: list[dict] = []


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
    # Smart-contract policy enforcement (RFC-0006, opt-in): if
    # LEDGER_RPC_URL + POLICY_CONTRACT_ADDRESS are configured, an on-chain
    # AEPXPolicyRegistry.sol reading wins; otherwise (the default) this is
    # a cheap env-var check that falls straight through to the seed policy
    # below, so behaviour is unchanged when unconfigured.
    max_risk_level = ledger.read_onchain_max_risk_level() or _POLICIES["max_risk_level"]
    try:
        requested_idx = _RISK_ORDER.index(level)
        max_idx = _RISK_ORDER.index(max_risk_level)
    except ValueError:
        return {"risk_level": risk_level, "allowed": False, "reason": "unrecognised risk level"}
    allowed = requested_idx <= max_idx
    return {"risk_level": risk_level, "allowed": allowed, "max_risk_level": max_risk_level}


@app.get("/audit")
def get_audit(limit: int = 200):
    conn = _get_conn()
    if conn:
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT id, topic, event, recorded_at FROM governance.audit_log "
                    "ORDER BY recorded_at DESC LIMIT %s",
                    (limit,),
                )
                rows = cur.fetchall()
            return [{"id": r[0], "topic": r[1], "event": r[2], "recorded_at": r[3].timestamp()} for r in rows]
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
            _maybe_anchor_pg(conn)
            return
        except Exception:
            pass
        finally:
            conn.close()
    audit_id = len(_AUDIT_FALLBACK) + 1
    _AUDIT_FALLBACK.append({"id": audit_id, "topic": topic, "event": event, "recorded_at": time.time()})
    _maybe_anchor_fallback()


def _maybe_anchor_pg(conn):
    # Anchoring is a hardening layer on top of the audit trail (Law 8) —
    # any failure here must never look like the audit write itself failed,
    # so every exception is swallowed.
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT COALESCE(MAX(last_audit_id), 0), COALESCE(MAX(seq_no), 0) FROM governance.ledger_anchors")
            last_anchored, last_seq = cur.fetchone()
            cur.execute(
                "SELECT id, topic, event FROM governance.audit_log WHERE id > %s ORDER BY id LIMIT %s",
                (last_anchored, _ANCHOR_BATCH_SIZE),
            )
            rows = cur.fetchall()
            if len(rows) < _ANCHOR_BATCH_SIZE:
                return
            cur.execute("SELECT anchor_hash FROM governance.ledger_anchors WHERE seq_no = %s", (last_seq,))
            prev_row = cur.fetchone()
            prev_hash = prev_row[0] if prev_row else ledger.GENESIS_HASH
            hashes = [ledger.event_hash(r[0], r[1], r[2]) for r in rows]
            root = ledger.merkle_root(hashes)
            local = _LOCAL_ANCHOR.anchor(prev_hash, root)
            tx_ref = _EVM_ANCHOR.anchor(root)
            cur.execute(
                "INSERT INTO governance.ledger_anchors "
                "(seq_no, prev_hash, merkle_root, anchor_hash, entry_count, first_audit_id, last_audit_id, backend, tx_ref) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (last_seq + 1, prev_hash, root, local["anchor_hash"], len(rows), rows[0][0], rows[-1][0],
                 local["backend"], tx_ref),
            )
    except Exception:
        pass


def _maybe_anchor_fallback():
    try:
        last_anchored = _LEDGER_FALLBACK[-1]["last_audit_id"] if _LEDGER_FALLBACK else 0
        pending = [e for e in _AUDIT_FALLBACK if e["id"] > last_anchored]
        if len(pending) < _ANCHOR_BATCH_SIZE:
            return
        batch = pending[:_ANCHOR_BATCH_SIZE]
        prev_hash = _LEDGER_FALLBACK[-1]["anchor_hash"] if _LEDGER_FALLBACK else ledger.GENESIS_HASH
        next_seq = (_LEDGER_FALLBACK[-1]["seq_no"] if _LEDGER_FALLBACK else 0) + 1
        hashes = [ledger.event_hash(e["id"], e["topic"], e["event"]) for e in batch]
        root = ledger.merkle_root(hashes)
        local = _LOCAL_ANCHOR.anchor(prev_hash, root)
        tx_ref = _EVM_ANCHOR.anchor(root)
        _LEDGER_FALLBACK.append({
            "seq_no": next_seq, "prev_hash": prev_hash, "merkle_root": root,
            "anchor_hash": local["anchor_hash"], "entry_count": len(batch),
            "first_audit_id": batch[0]["id"], "last_audit_id": batch[-1]["id"],
            "backend": local["backend"], "tx_ref": tx_ref, "anchored_at": time.time(),
        })
    except Exception:
        pass


@app.get("/ledger/anchors")
def list_anchors(limit: int = 50):
    conn = _get_conn()
    if conn:
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT seq_no, prev_hash, merkle_root, anchor_hash, entry_count, first_audit_id, "
                    "last_audit_id, backend, tx_ref, anchored_at FROM governance.ledger_anchors "
                    "ORDER BY seq_no DESC LIMIT %s",
                    (limit,),
                )
                rows = cur.fetchall()
            return [
                {"seq_no": r[0], "prev_hash": r[1], "merkle_root": r[2], "anchor_hash": r[3],
                 "entry_count": r[4], "first_audit_id": r[5], "last_audit_id": r[6],
                 "backend": r[7], "tx_ref": r[8], "anchored_at": r[9].timestamp()}
                for r in rows
            ]
        except Exception:
            pass
        finally:
            conn.close()
    return list(reversed(_LEDGER_FALLBACK))[:limit]


@app.get("/ledger/verify/{audit_id}")
def verify_anchor(audit_id: int):
    anchors = sorted(list_anchors(limit=10_000), key=lambda a: a["seq_no"])
    match = next((a for a in anchors if a["first_audit_id"] <= audit_id <= a["last_audit_id"]), None)
    if not match:
        return {"audit_id": audit_id, "anchored": False, "chain_valid": None, "anchor": None}

    # Replay the local hash chain from genesis — this is the actual
    # tamper-evidence check: if any historical anchor_hash doesn't match
    # what LocalHashChainAnchor recomputes from its neighbours, the audit
    # trail has been altered since it was anchored.
    chain_valid = True
    prev_hash = ledger.GENESIS_HASH
    for a in anchors:
        if a["prev_hash"] != prev_hash:
            chain_valid = False
            break
        expected = _LOCAL_ANCHOR.anchor(prev_hash, a["merkle_root"])["anchor_hash"]
        if expected != a["anchor_hash"]:
            chain_valid = False
            break
        prev_hash = a["anchor_hash"]
        if a["seq_no"] == match["seq_no"]:
            break

    return {"audit_id": audit_id, "anchored": True, "chain_valid": chain_valid, "anchor": match}


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
    while True:
        try:
            consumer = KafkaConsumer(*_CONSUMED_TOPICS, bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP", "kafka:9092"),
                                      auto_offset_reset="earliest",
                                      value_deserializer=lambda v: json.loads(v.decode()))
            for msg in consumer:
                _record(msg.topic, msg.value)
        except Exception:
            time.sleep(5)


threading.Thread(target=consume_all_events, daemon=True).start()
