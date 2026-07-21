"""AEP-X Workbench — the utilisation platform (RFC-0007).

A developer portal over the live protocol: send RFC-0001 envelopes to any
catalogued connector through the full trust/policy/circuit chain, mint and
resolve did:key identities, inspect trust scores, verify ledger anchors,
and tail the Law 8 audit trail. The backend proxies via the SDK because
the browser can't reach docker-internal hostnames.
"""
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from aepx import AepxClient

app = FastAPI(title="AEP-X Workbench — utilisation platform", version="0.1.0")

client = AepxClient(
    gateway_url=os.getenv("GATEWAY_URL", "http://gateway:8000"),
    identity_url=os.getenv("IDENTITY_URL", "http://identity:8000"),
    trust_url=os.getenv("TRUST_URL", "http://trust:8000"),
    registry_url=os.getenv("REGISTRY_URL", "http://registry:8000"),
    governance_url=os.getenv("GOVERNANCE_URL", "http://governance:8000"),
    bus_url=os.getenv("CONNECTOR_BUS_URL", "http://connector-bus:8000"),
    timeout=35.0,  # a real model completion through the bus can take 15s+
)


def _proxied(fn, *args, **kwargs):
    # One degrade-don't-fail wrapper for every pass-through: an unreachable
    # backing service becomes a clean 502 with the reason, never a raw 500.
    try:
        return fn(*args, **kwargs)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"backing service unreachable: {type(e).__name__}: {e}")


class InvokeRequest(BaseModel):
    connector: str
    payload: dict = {}
    sender: str = "aepx://agent/workbench"


class AgentRequest(BaseModel):
    name: str
    did: str | None = None


@app.get("/health")
def health():
    return {"status": "ok", "service": "workbench"}


@app.get("/api/connectors")
def connectors():
    return _proxied(client.connectors.list)


@app.post("/api/invoke")
def invoke(req: InvokeRequest):
    # Denials (403 trust/policy, 503 circuit) come back as structured
    # results — in a protocol workbench a governed denial is a first-class
    # outcome to display, not an error to mask.
    return _proxied(client.connectors.invoke, req.connector, req.payload, sender=req.sender)


@app.post("/api/did")
def create_did():
    return _proxied(client.did.create)


@app.get("/api/did/{did:path}")
def resolve_did(did: str):
    return _proxied(client.did.resolve, did)


@app.get("/api/trust/{entity_id}")
def trust(entity_id: str):
    return _proxied(client.trust.get, entity_id)


@app.get("/api/ledger/anchors")
def anchors(limit: int = 50):
    return _proxied(client.ledger.anchors, limit)


@app.get("/api/ledger/verify/{audit_id}")
def verify(audit_id: int):
    return _proxied(client.ledger.verify, audit_id)


@app.get("/api/audit")
def audit(limit: int = 50):
    return _proxied(client.audit.tail, limit)


@app.get("/api/agents")
def agents():
    def _list():
        resp = client._request("GET", f"{client.registry_url}/agents")
        resp.raise_for_status()
        return resp.json()
    return _proxied(_list)


@app.post("/api/agents")
def register_agent(req: AgentRequest):
    def _create():
        resp = client._request("POST", f"{client.registry_url}/agents",
                               json={"name": req.name, "did": req.did})
        resp.raise_for_status()
        return resp.json()
    return _proxied(_create)


_STATIC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.isdir(_STATIC):
    @app.get("/")
    def index():
        return FileResponse(os.path.join(_STATIC, "index.html"))

    app.mount("/static", StaticFiles(directory=_STATIC), name="static")
