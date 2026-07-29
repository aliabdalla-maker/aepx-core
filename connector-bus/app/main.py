from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
import json
import os
import time
import uuid

app = FastAPI(title="AEP-X Connector Bus (ACB)", version="0.2.0")

TRUST_URL = os.getenv("TRUST_URL", "http://trust:8000")
GOVERNANCE_URL = os.getenv("GOVERNANCE_URL", "http://governance:8000")
BRAIN_URL = os.getenv("BRAIN_URL", "http://brain:8000")
CATALOGUE_PATH = os.getenv("CATALOGUE_PATH", "/app/catalogue.json")

try:
    from kafka import KafkaProducer
    _KAFKA_IMPORTABLE = True
except Exception:
    _KAFKA_IMPORTABLE = False

_producer = None


def _get_producer():
    # Lazy + retried — see services/workflow/app/main.py for why a
    # created-once-at-import producer silently loses events on the broker
    # startup race.
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


def _load_connectors() -> dict:
    # Content-based routing table — data, not code (SOA-Architecture.md
    # §3.3). Routing is by convention: connector -> its category service at
    # http://connector-{category}:8000, overridable per category via
    # CONNECTOR_URL_{CATEGORY} for local/hybrid deployments.
    try:
        with open(CATALOGUE_PATH, encoding="utf-8") as f:
            catalogue = json.load(f)
    except Exception:
        return {}
    connectors = {}
    for c in catalogue["connectors"]:
        category = c["category"]
        base_url = os.getenv(f"CONNECTOR_URL_{category.upper()}", f"http://connector-{category}:8000")
        connectors[c["name"]] = {
            "category": category,
            "base_url": base_url,
            "ai_risk_class": c["ai_risk_class"],
            "min_trust_score": c["min_trust_score"],
            "maturity": c.get("maturity", "stub"),
        }
    return connectors


CONNECTORS = _load_connectors()


class Envelope(BaseModel):
    # RFC-0001 message envelope, reused verbatim — see SOA-Architecture.md §3.1.
    version: str = "1.0"
    sender: str
    receiver: str  # e.g. "aepx://connector/salesforce"
    messageType: str = "request"
    payload: dict
    metadata: dict = {}


def _connector_name_from_receiver(receiver: str) -> str:
    # aepx://connector/{name}
    parts = receiver.rstrip("/").split("/")
    return parts[-1]


@app.get("/health")
def health():
    categories = sorted({c["category"] for c in CONNECTORS.values()})
    return {
        "status": "ok",
        "service": "connector-bus",
        "connector_count": len(CONNECTORS),
        "categories": categories,
        "connectors": sorted(CONNECTORS),
    }


@app.post("/bus/route")
async def route(envelope: Envelope):
    name = _connector_name_from_receiver(envelope.receiver)
    connector = CONNECTORS.get(name)
    if not connector:
        raise HTTPException(404, f"unknown connector '{name}' — not in catalogue")

    agent_id = envelope.sender.rstrip("/").split("/")[-1]

    # Governance checks are in-memory lookups and must fail fast (3s); the
    # connector forward can be a real model/API call and needs real headroom
    # (30s) — a live inference taking 3-15s must not look like a bus outage.
    async with httpx.AsyncClient(timeout=3.0) as client:
        # 1. Trust check — Law 2, Trust Before Execution.
        trust_resp = await client.get(f"{TRUST_URL}/trust/{agent_id}")
        trust_score = trust_resp.json().get("trust_score", 0)
        if trust_score < connector["min_trust_score"]:
            await _audit(agent_id, name, "denied", "trust_below_threshold", trust_score, connector["ai_risk_class"])
            raise HTTPException(403, f"trust score {trust_score} below required {connector['min_trust_score']} for connector '{name}'")

        # 2. Policy check — Law 8, Auditability, enforced structurally here
        #    rather than by convention (SOA-Architecture.md §3.1 rule 4).
        policy_resp = await client.post(
            f"{GOVERNANCE_URL}/policy/evaluate",
            params={"risk_level": connector["ai_risk_class"]},
        )
        policy = policy_resp.json() if policy_resp.status_code == 200 else {"allowed": False}
        if not policy.get("allowed", False):
            await _audit(agent_id, name, "denied", "policy_denied", trust_score, connector["ai_risk_class"])
            raise HTTPException(403, f"policy denies risk level {connector['ai_risk_class']} for connector '{name}'")

        # 3. Circuit breaker — self-healing (services/brain): if this connector
        # has been failing repeatedly, fail fast with a clear reason instead of
        # every caller re-discovering the same timeout. Fail-open: the Brain
        # being unreachable must never itself block a normal call.
        try:
            circuit_resp = await client.get(f"{BRAIN_URL}/brain/circuit/{name}")
            circuit = circuit_resp.json()
            if not circuit.get("allowed", True):
                await _audit(agent_id, name, "denied", "circuit_open", trust_score, connector["ai_risk_class"])
                raise HTTPException(503, f"connector '{name}' is circuit-broken (reliability {circuit.get('reliability_score')}) — try again later")
        except HTTPException:
            raise
        except Exception:
            pass  # Brain unreachable — fail open, proceed as normal

        # 4. Mediate — forward the canonical envelope to the owning category
        #    service, which dispatches to the connector's adapter. Overrides
        #    the client's 3s default for this call only.
        forward_resp = await client.post(
            f"{connector['base_url']}/connector/execute", json=envelope.model_dump(), timeout=30.0
        )

        await _audit(agent_id, name, "invoked", None, trust_score, connector["ai_risk_class"])
        # Real usage bumps trust a little — a flat default forever would make
        # the console's "ranked active agents" panel meaningless. Best-effort:
        # a Trust hiccup must never fail the connector call itself.
        try:
            await client.post(f"{TRUST_URL}/trust/{agent_id}/adjust", json={"component": "behaviour", "delta": 1})
        except Exception:
            pass

    return {
        "connector": name,
        "category": connector["category"],
        "ai_risk_class": connector["ai_risk_class"],
        "maturity": connector["maturity"],
        "trust_score_at_call_time": trust_score,
        "response": forward_resp.json(),
    }


async def _audit(agent_id, connector_name, outcome, reason, trust_score=None, ai_risk_class=None):
    # Publishes to the same Kafka bus the microservices core already runs,
    # so Governance Engine's "consume every topic" pattern (Microservices
    # Guide §4.2) picks this up for free — connector.invoked/connector.denied
    # are already in its topic list, waiting for a real producer.
    event = {
        "id": str(uuid.uuid4()),
        "agent_id": agent_id,
        "connector": connector_name,
        "outcome": outcome,
        "reason": reason,
        "trust_score": trust_score,
        "ai_risk_class": ai_risk_class,
        "ts": time.time(),
    }
    topic = "connector.invoked" if outcome == "invoked" else "connector.failed"
    producer = _get_producer()
    if producer:
        producer.send(topic, event)
