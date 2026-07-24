"""AEP-X Oracle Bridge — the chain→AI direction of the bridge (RFC-0008).

An on-chain AEPXOracle.sol caller requests an AI decision; this service is
the off-chain half that actually produces it:

  1. runs a **governed** AI call — routed through the Connector Bus to the
     ``ml`` connector, so Law 2 (Trust Before Execution) and Law 8
     (Auditability) apply to the model call exactly as they do to any other
     connector invocation; the bridge never talks to a model directly;
  2. scores the answer through the **Verification Engine** (truth score +
     GREEN/AMBER/RED/GREY band) — this is the "evidence-scored answer" the
     bridge writes back, not a raw completion;
  3. writes the result back on-chain via the permissioned
     ``fulfillDecision`` (only when a chain is configured).

Degrade-clean, like everything else in this repo: with no chain configured
(the default) the on-chain listener idles and ``POST /oracle/decide`` still
serves the full off-chain pipeline; if the AI or Verification call fails,
the decision comes back as band ``GREY`` / confidence ``0`` rather than a
5xx. Nothing here requires infrastructure the reference stack can't stand
up itself (RFC-0008 §3).
"""
import json
import os
import threading
import time

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="AEP-X Oracle Bridge", version="0.1.0")

BUS_URL = os.getenv("CONNECTOR_BUS_URL", "http://connector-bus:8000")
VERIFICATION_URL = os.getenv("VERIFICATION_URL", "http://verification:8000")
AI_CONNECTOR = os.getenv("ORACLE_AI_CONNECTOR", "ml")
SENDER = "aepx://agent/oracle-bridge"

# On-chain listener config — all optional. Unset (default) => listener idle.
ORACLE_RPC_URL = os.getenv("ORACLE_RPC_URL")
ORACLE_CONTRACT_ADDRESS = os.getenv("ORACLE_CONTRACT_ADDRESS")
ORACLE_PRIVATE_KEY = os.getenv("ORACLE_PRIVATE_KEY")
POLL_INTERVAL = float(os.getenv("ORACLE_POLL_INTERVAL", "15"))

# Recent decisions kept in memory for /oracle/history — the chain (when
# configured) and Governance's audit log are the durable records; this is
# just an operator convenience, so no new SQL table (RFC-0008 §5).
_HISTORY: list[dict] = []
_HISTORY_MAX = 200

try:
    from kafka import KafkaProducer
    _KAFKA_IMPORTABLE = True
except Exception:
    _KAFKA_IMPORTABLE = False

_producer = None

# Minimal ABI — only what the bridge reads/writes on AEPXOracle.sol.
_ORACLE_ABI = [
    {"inputs": [], "name": "nextRequestId", "outputs": [{"name": "", "type": "uint256"}],
     "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "requestId", "type": "uint256"}], "name": "getDecision",
     "outputs": [{"components": [
         {"name": "requester", "type": "address"},
         {"name": "prompt", "type": "string"},
         {"name": "answer", "type": "string"},
         {"name": "confidence", "type": "uint8"},
         {"name": "band", "type": "string"},
         {"name": "fulfilled", "type": "bool"},
         {"name": "requestedAt", "type": "uint256"},
         {"name": "fulfilledAt", "type": "uint256"}],
         "name": "", "type": "tuple"}],
     "stateMutability": "view", "type": "function"},
    {"inputs": [
        {"name": "requestId", "type": "uint256"},
        {"name": "answer", "type": "string"},
        {"name": "confidence", "type": "uint8"},
        {"name": "band", "type": "string"}],
     "name": "fulfillDecision", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"anonymous": False, "inputs": [
        {"indexed": True, "name": "requestId", "type": "uint256"},
        {"indexed": True, "name": "requester", "type": "address"},
        {"indexed": False, "name": "prompt", "type": "string"}],
     "name": "DecisionRequested", "type": "event"},
]

# Log-based scanning is the default (RFC-0008 §9): react to DecisionRequested
# events instead of rescanning every request id each cycle. Falls back to an
# id-scan if the node/filter API misbehaves. _LAST_BLOCK tracks how far the
# log scan has advanced so each cycle only reads new blocks.
USE_LOGS = os.getenv("ORACLE_USE_LOGS", "true").lower() in ("1", "true", "yes")
_LAST_BLOCK = 0


def _get_web3():
    # Lazy — see services/governance/app/ledger.py: web3's import alone is
    # heavy, and a bridge with no chain configured (the default) must not
    # pay it just to serve /oracle/decide.
    try:
        from web3 import Web3
        return Web3
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


def _publish(topic: str, event: dict):
    producer = _get_producer()
    if producer:
        try:
            producer.send(topic, event)
        except Exception:
            pass


def _chain_configured() -> bool:
    return bool(ORACLE_RPC_URL and ORACLE_CONTRACT_ADDRESS and ORACLE_PRIVATE_KEY)


class DecideIn(BaseModel):
    prompt: str
    request_id: int | None = None  # set when this decision answers an on-chain request


def decide(prompt: str, request_id=None) -> dict:
    """The core pipeline, shared by the HTTP endpoint and the on-chain
    listener: governed AI call -> verification scoring -> scored answer.
    Never raises — a failure in either downstream call degrades the band to
    GREY / confidence 0 with a reason, so callers (and the chain) always get
    a well-formed decision."""
    _publish("oracle.requested", {"request_id": request_id, "prompt": prompt[:500], "ts": time.time()})

    # 1. Governed AI call through the Connector Bus (trust + policy + audit).
    answer, ai_source, ai_reason = _governed_ai_call(prompt)

    # 2. Evidence/verification scoring. The answer's provenance (the model
    #    source) is its evidence at this stage; the Verification Engine turns
    #    that into a truth score + band (RFC-0007). Richer evidence
    #    correlation is a later upgrade, same as Verification's own scaffold.
    confidence, band, verify_reason = _verify(answer, ai_source, request_id)

    decision = {
        "request_id": request_id,
        "prompt": prompt,
        "answer": answer,
        "confidence": confidence,       # 0-100, uint8-safe for on-chain fulfil
        "band": band,                   # GREEN | AMBER | RED | GREY
        "ai_source": ai_source,
        "reason": ai_reason or verify_reason,
        "ts": time.time(),
    }
    _remember(decision)
    return decision


def _governed_ai_call(prompt: str):
    envelope = {
        "version": "1.0",
        "sender": SENDER,
        "receiver": f"aepx://connector/{AI_CONNECTOR}",
        "messageType": "request",
        "payload": {"prompt": prompt},
        "metadata": {},
    }
    try:
        resp = httpx.post(f"{BUS_URL}/bus/route", json=envelope, timeout=30.0)
        if resp.status_code != 200:
            # A 403/503 here is a governance outcome (trust/policy/circuit),
            # not a transport error — surface it as the reason, don't hide it.
            try:
                reason = resp.json().get("detail")
            except Exception:
                reason = resp.text
            return "", f"connector:{AI_CONNECTOR}", f"ai_call_denied ({resp.status_code}): {reason}"
        body = resp.json().get("response", {})
        return body.get("result", ""), body.get("source", f"connector:{AI_CONNECTOR}"), None
    except Exception as e:
        return "", f"connector:{AI_CONNECTOR}", f"ai_call_unreachable ({type(e).__name__})"


def _verify(answer: str, ai_source: str, request_id):
    if not answer:
        return 0, "GREY", "no_answer_to_verify"
    verify_body = {
        "workflow_id": f"oracle-{request_id if request_id is not None else 'adhoc'}",
        "claims": [{"text": answer, "source_ids": [ai_source]}],
    }
    try:
        resp = httpx.post(f"{VERIFICATION_URL}/verify", json=verify_body, timeout=10.0)
        resp.raise_for_status()
        summary = resp.json().get("summary", {})
        confidence = int(round(min(100.0, max(0.0, float(summary.get("truth_score", 0.0))))))
        band = summary.get("confidence_band", "GREY")
        return confidence, band, None
    except Exception as e:
        # Verification down: return the answer but mark it unscored, rather
        # than fail the whole decision.
        return 0, "GREY", f"verification_unreachable ({type(e).__name__})"


def _remember(decision: dict):
    _HISTORY.append(decision)
    if len(_HISTORY) > _HISTORY_MAX:
        del _HISTORY[: len(_HISTORY) - _HISTORY_MAX]


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "oracle-bridge",
        "chain_configured": _chain_configured(),
        "ai_connector": AI_CONNECTOR,
        "decisions_seen": len(_HISTORY),
    }


@app.post("/oracle/decide")
def oracle_decide(body: DecideIn):
    """Run the off-chain pipeline directly — no chain required. This is the
    always-on path and what the tests exercise."""
    return decide(body.prompt, body.request_id)


@app.get("/oracle/history")
def oracle_history(limit: int = 50):
    return list(reversed(_HISTORY))[:limit]


@app.post("/oracle/poll")
def oracle_poll():
    """Run a single on-chain poll cycle on demand (also what the background
    loop calls). Returns a summary; a no-op when no chain is configured."""
    return _poll_once()


def _connect():
    Web3 = _get_web3()
    if Web3 is None:
        raise RuntimeError("web3 not importable")
    w3 = Web3(Web3.HTTPProvider(ORACLE_RPC_URL, request_kwargs={"timeout": 5}))
    account = w3.eth.account.from_key(ORACLE_PRIVATE_KEY)
    contract = w3.eth.contract(address=Web3.to_checksum_address(ORACLE_CONTRACT_ADDRESS), abi=_ORACLE_ABI)
    return w3, contract, account


def _fulfill(w3, contract, account, request_id: int, prompt: str) -> bool:
    """Decide + write back on-chain for one request. Returns True if it wrote
    a fulfilment, False if the request was already fulfilled."""
    d = contract.functions.getDecision(request_id).call()
    if d[5]:  # already fulfilled
        return False
    decision = decide(prompt or d[1], request_id)
    tx = contract.functions.fulfillDecision(
        request_id, decision["answer"], decision["confidence"], decision["band"]
    ).build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
    })
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    _publish("oracle.fulfilled", {
        "request_id": request_id, "band": decision["band"],
        "confidence": decision["confidence"], "tx_hash": tx_hash.hex(), "ts": time.time(),
    })
    return True


def _poll_via_logs(w3, contract, account) -> dict:
    """React to DecisionRequested events since the last scanned block."""
    global _LAST_BLOCK
    latest = w3.eth.block_number
    from_block = _LAST_BLOCK
    events = contract.events.DecisionRequested().get_logs(from_block=from_block, to_block=latest)
    processed = 0
    for ev in events:
        if _fulfill(w3, contract, account, ev["args"]["requestId"], ev["args"]["prompt"]):
            processed += 1
    _LAST_BLOCK = latest + 1
    return {"chain_configured": True, "mode": "logs", "processed": processed,
            "scanned_to_block": latest}


def _poll_by_ids(w3, contract, account) -> dict:
    """Fallback: scan every request id (deterministic, filter-API-independent)."""
    total = contract.functions.nextRequestId().call()
    processed = sum(1 for rid in range(total) if _fulfill(w3, contract, account, rid, ""))
    return {"chain_configured": True, "mode": "ids", "processed": processed, "total_requests": total}


def _poll_once() -> dict:
    if not _chain_configured():
        return {"chain_configured": False, "processed": 0, "reason": "oracle chain not configured"}
    try:
        w3, contract, account = _connect()
    except Exception as e:
        return {"chain_configured": True, "processed": 0, "reason": f"connect_failed ({type(e).__name__})"}
    if USE_LOGS:
        try:
            return _poll_via_logs(w3, contract, account)
        except Exception:
            # Some nodes / filter APIs differ; fall back to the id-scan rather
            # than miss requests (RFC-0008 §9).
            pass
    try:
        return _poll_by_ids(w3, contract, account)
    except Exception as e:
        return {"chain_configured": True, "processed": 0, "reason": f"poll_failed ({type(e).__name__})"}


def _listen_loop():
    # Only runs when a chain is configured; otherwise the thread exits
    # immediately (the off-chain /oracle/decide path is unaffected).
    if not _chain_configured():
        return
    while True:
        try:
            _poll_once()
        except Exception:
            pass
        time.sleep(POLL_INTERVAL)


threading.Thread(target=_listen_loop, daemon=True).start()
