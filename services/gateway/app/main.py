from fastapi import FastAPI
import httpx
import os

app = FastAPI(title="AEP-X Gateway", version="0.0.1")
SERVICES = {
    "identity": os.getenv("IDENTITY_URL", "http://identity:8000"),
    "trust": os.getenv("TRUST_URL", "http://trust:8000"),
    "registry": os.getenv("REGISTRY_URL", "http://registry:8000"),
    "memory": os.getenv("MEMORY_URL", "http://memory:8000"),
    "cache": os.getenv("CACHE_URL", "http://cache:8000"),
    "discovery": os.getenv("DISCOVERY_URL", "http://discovery:8000"),
    "workflow": os.getenv("WORKFLOW_URL", "http://workflow:8000"),
    "safety": os.getenv("SAFETY_URL", "http://safety:8000"),
    "governance": os.getenv("GOVERNANCE_URL", "http://governance:8000"),
    "knowledge": os.getenv("KNOWLEDGE_URL", "http://knowledge:8000"),
    "verification": os.getenv("VERIFICATION_URL", "http://verification:8000"),
    "cost-optimiser": os.getenv("COST_OPTIMISER_URL", "http://cost-optimiser:8000"),
    "ml-integration": os.getenv("ML_INTEGRATION_URL", "http://ml-integration:8000"),
    "oracle-bridge": os.getenv("ORACLE_BRIDGE_URL", "http://oracle-bridge:8000"),
    "connector-bus": os.getenv("CONNECTOR_BUS_URL", "http://connector-bus:8000"),
}


@app.get("/health")
async def health():
    results = {}
    async with httpx.AsyncClient(timeout=2.0) as client:
        for name, base in SERVICES.items():
            try:
                results[name] = (await client.get(f"{base}/health")).json()
            except Exception as e:
                results[name] = {"status": "down", "error": str(e)}
    return results


@app.post("/execute")
async def execute(agent_id: str, capability: str, payload: dict):
    # v0.0.1: passthrough only. Cache-first routing (RFC-0008 hierarchy,
    # now implemented by services/cost-optimiser) lands once wired here.
    async with httpx.AsyncClient(timeout=5.0) as client:
        agent = await client.get(f"{SERVICES['registry']}/agents/{agent_id}")
        return {"agent": agent.json(), "capability": capability, "payload": payload}
