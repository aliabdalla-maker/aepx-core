"""AEP-X Console — the whole-platform control surface.

A single-page GUI over the entire running stack, not just one subsystem:
overview health of every service, the connector catalogue + governed
invocation, trust & did:key identity, memory, discovery & workflows,
governance / audit / ledger, the RFC-0008 AI<->chain bridge, and an LLM
chat box that routes through the bus. The backend proxies through the SDK
(for the plugin-covered subsystems) and directly to each service's REST API
(for the rest), because a browser can't reach docker-internal hostnames.

Every proxy degrades to a clean 502 with a reason (never a raw 500), and
the health grid catches each target independently so one down service never
blanks the whole board — the same discipline as platform/workbench.
"""
import os

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from aepx import AepxClient
from aepx.plugins import OraclePlugin

app = FastAPI(title="AEP-X Console", version="1.0.0")

client = AepxClient(
    gateway_url=os.getenv("GATEWAY_URL", "http://gateway:8000"),
    identity_url=os.getenv("IDENTITY_URL", "http://identity:8000"),
    trust_url=os.getenv("TRUST_URL", "http://trust:8000"),
    registry_url=os.getenv("REGISTRY_URL", "http://registry:8000"),
    governance_url=os.getenv("GOVERNANCE_URL", "http://governance:8000"),
    bus_url=os.getenv("CONNECTOR_BUS_URL", "http://connector-bus:8000"),
    timeout=40.0,
)
client.use(OraclePlugin(oracle_url=os.getenv("ORACLE_BRIDGE_URL", "http://oracle-bridge:8000")))

# Every service the console talks to, by in-cluster URL. One place so the
# health grid, the generic proxy, and per-section calls all agree.
SVC = {
    "gateway": client.gateway_url,
    "identity": client.identity_url,
    "trust": client.trust_url,
    "registry": client.registry_url,
    "memory": os.getenv("MEMORY_URL", "http://memory:8000"),
    "cache": os.getenv("CACHE_URL", "http://cache:8000"),
    "discovery": os.getenv("DISCOVERY_URL", "http://discovery:8000"),
    "workflow": os.getenv("WORKFLOW_URL", "http://workflow:8000"),
    "safety": os.getenv("SAFETY_URL", "http://safety:8000"),
    "governance": client.governance_url,
    "knowledge": os.getenv("KNOWLEDGE_URL", "http://knowledge:8000"),
    "verification": os.getenv("VERIFICATION_URL", "http://verification:8000"),
    "cost-optimiser": os.getenv("COST_OPTIMISER_URL", "http://cost-optimiser:8000"),
    "ml-integration": os.getenv("ML_INTEGRATION_URL", "http://ml-integration:8000"),
    "brain": os.getenv("BRAIN_URL", "http://brain:8000"),
    "marketplace": os.getenv("MARKETPLACE_URL", "http://marketplace:8000"),
    "billing": os.getenv("BILLING_URL", "http://billing:8000"),
    "oracle-bridge": client.oracle.oracle_url,
    "connector-bus": client.bus_url,
    "blockchain-connector": os.getenv("CONNECTOR_URL_BLOCKCHAIN", "http://connector-blockchain:8000"),
}


def _proxied(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"backing service unreachable: {type(e).__name__}: {e}")


def _svc_get(name: str, path: str, **params):
    def _do():
        r = httpx.get(f"{SVC[name]}{path}", params=params or None, timeout=10.0)
        r.raise_for_status()
        return r.json()
    return _proxied(_do)


def _svc_post(name: str, path: str, body: dict | None = None, **params):
    def _do():
        r = httpx.post(f"{SVC[name]}{path}", json=body, params=params or None, timeout=35.0)
        r.raise_for_status()
        return r.json()
    return _proxied(_do)


# ---- request models ------------------------------------------------------
class ContractRequest(BaseModel):
    connector: str = "ethereum"
    address: str
    abi: list = []
    function: str
    args: list = []
    sender: str = "aepx://agent/console"


class RpcRequest(BaseModel):
    connector: str = "ethereum"
    method: str = "eth_blockNumber"
    params: list = []
    sender: str = "aepx://agent/console"


class DecideRequest(BaseModel):
    prompt: str
    request_id: int | None = None


class InvokeRequest(BaseModel):
    connector: str
    payload: dict = {}
    sender: str = "aepx://agent/console"


class AgentRequest(BaseModel):
    name: str
    did: str | None = None


class MemoryRequest(BaseModel):
    agent_id: str
    content: dict


class WorkflowRequest(BaseModel):
    name: str
    steps: list = []


class ChatRequest(BaseModel):
    prompt: str
    sender: str = "aepx://agent/console"


class PredictRequest(BaseModel):
    kind: str = "cost"
    features: dict = {}


@app.get("/health")
def health():
    return {"status": "ok", "service": "aepx-console"}


# ---- overview ------------------------------------------------------------
@app.get("/api/health-map")
async def health_map():
    # Probe every service concurrently, not sequentially — with ~18 targets
    # and a 2s per-target timeout, a serial sweep would take ~36s during a
    # full outage (exactly when an operator opens the console) and would
    # starve every other request. asyncio.gather bounds the whole sweep to
    # roughly one timeout regardless of how many services are down.
    import asyncio

    async def probe(hc, label, base):
        try:
            r = await hc.get(f"{base}/health")
            body = r.json()
            return label, {"up": body.get("status") == "ok", "detail": body}
        except Exception as e:
            return label, {"up": False, "detail": {"error": type(e).__name__}}

    async with httpx.AsyncClient(timeout=2.0) as hc:
        results = await asyncio.gather(*(probe(hc, label, base) for label, base in SVC.items()))
    return dict(results)


# ---- connectors ----------------------------------------------------------
@app.get("/api/connectors")
def connectors():
    return _proxied(client.connectors.list)


@app.post("/api/invoke")
def invoke(req: InvokeRequest):
    return _proxied(client.connectors.invoke, req.connector, req.payload, sender=req.sender)


# ---- trust & identity ----------------------------------------------------
@app.get("/api/trust/{entity_id}")
def trust(entity_id: str):
    return _proxied(client.trust.get, entity_id)


@app.post("/api/did")
def create_did():
    return _proxied(client.did.create)


@app.get("/api/did/{did:path}")
def resolve_did(did: str):
    return _proxied(client.did.resolve, did)


@app.get("/api/agents")
def agents():
    return _svc_get("registry", "/agents")


@app.post("/api/agents")
def register_agent(req: AgentRequest):
    return _svc_post("registry", "/agents", {"name": req.name, "did": req.did})


# ---- memory, discovery, workflows ---------------------------------------
@app.post("/api/memory")
def memory_write(req: MemoryRequest):
    return _svc_post("memory", "/memory/session", {"agent_id": req.agent_id, "content": req.content})


@app.get("/api/memory/{agent_id}")
def memory_read(agent_id: str):
    return _svc_get("memory", f"/memory/session/{agent_id}")


@app.get("/api/discover")
def discover(capability: str):
    return _svc_get("discovery", "/discover", capability=capability)


@app.post("/api/workflow")
def workflow_create(req: WorkflowRequest):
    return _svc_post("workflow", "/workflows", {"name": req.name, "steps": req.steps})


@app.post("/api/workflow/{wf_id}/execute")
def workflow_execute(wf_id: str):
    return _svc_post("workflow", f"/workflows/{wf_id}/execute")


# ---- governance / audit / ledger ----------------------------------------
@app.get("/api/policy")
def policy(risk_level: str):
    return _svc_post("governance", "/policy/evaluate", None, risk_level=risk_level)


@app.get("/api/audit")
def audit(limit: int = 30):
    return _proxied(client.audit.tail, limit)


@app.get("/api/ledger/anchors")
def anchors(limit: int = 25):
    return _proxied(client.ledger.anchors, limit)


@app.get("/api/ledger/verify/{audit_id}")
def verify_anchor(audit_id: int):
    return _proxied(client.ledger.verify, audit_id)


# ---- ML / brain ----------------------------------------------------------
@app.get("/api/models")
def models():
    return _svc_get("ml-integration", "/models")


@app.post("/api/predict")
def predict(req: PredictRequest):
    return _svc_post("ml-integration", "/predict", {"kind": req.kind, "features": req.features})


@app.get("/api/brain/status")
def brain_status():
    return _svc_get("brain", "/brain/status")


@app.get("/api/brain/reliability")
def brain_reliability():
    return _svc_get("brain", "/brain/reliability")


# ---- AI <-> chain bridge (RFC-0008) -------------------------------------
@app.post("/api/chain/read")
def chain_read(req: ContractRequest):
    return _proxied(client.chain.read, req.address, req.abi, req.function, req.args,
                    connector=req.connector, sender=req.sender)


@app.post("/api/chain/write")
def chain_write(req: ContractRequest):
    return _proxied(client.chain.write, req.address, req.abi, req.function, req.args,
                    connector=req.connector, sender=req.sender)


@app.post("/api/chain/rpc")
def chain_rpc(req: RpcRequest):
    return _proxied(client.chain.rpc, req.method, req.params, connector=req.connector, sender=req.sender)


@app.post("/api/chain/status")
def chain_status(req: RpcRequest):
    # A consolidated live chain snapshot for the Blockchain overview — three
    # standard reads through the governed bus. Each call is caught
    # independently so an unreachable node yields a clean node_up=false
    # snapshot rather than a 502; the connector's own degraded fallback also
    # keeps a cold chain from ever 5xx-ing (connectors/blockchain).
    out = {"connector": req.connector, "node_up": False}
    for key, method in (("block", "eth_blockNumber"), ("chain_id", "eth_chainId"), ("gas_price", "eth_gasPrice")):
        try:
            r = client.chain.rpc(method, [], connector=req.connector, sender=req.sender)
            resp = r.get("response", {}) if isinstance(r, dict) else {}
            out[key] = resp.get("result")
            out["maturity"] = resp.get("maturity")
            if resp.get("maturity") == "specialized":
                out["node_up"] = True
        except Exception as e:
            out[key] = None
            out.setdefault("error", type(e).__name__)
    return out


@app.post("/api/oracle/decide")
def oracle_decide(req: DecideRequest):
    return _proxied(client.oracle.decide, req.prompt, req.request_id)


@app.post("/api/oracle/poll")
def oracle_poll():
    return _proxied(client.oracle.poll)


@app.get("/api/oracle/history")
def oracle_history(limit: int = 25):
    return _proxied(client.oracle.history, limit)


# ---- LLM console ---------------------------------------------------------
@app.post("/api/chat")
def chat(req: ChatRequest):
    # Route the prompt through the bus to the self-hosted `ml` connector, so
    # even a chat message is trust/policy/audit-governed like any other call.
    return _proxied(client.connectors.invoke, "ml", {"prompt": req.prompt}, sender=req.sender)


_STATIC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.isdir(_STATIC):
    @app.get("/")
    def index():
        return FileResponse(os.path.join(_STATIC, "index.html"))

    app.mount("/static", StaticFiles(directory=_STATIC), name="static")
