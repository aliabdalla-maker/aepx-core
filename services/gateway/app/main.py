from fastapi import FastAPI, HTTPException
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
    "marketplace": os.getenv("MARKETPLACE_URL", "http://marketplace:8000"),
    "billing": os.getenv("BILLING_URL", "http://billing:8000"),
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


# RFC-0008 reuse-before-computation hierarchy, cheapest first. Must stay in
# sync with services/cost-optimiser ROUTES.
ROUTES = ["cache", "memory", "knowledge", "workflow", "tool", "small_model", "medium_model", "large_model", "human"]
# Tiers scored when the caller doesn't pin one. Order matters: on a utility
# tie the earlier (cheaper) tier wins — cache-first routing (Law 5).
DEFAULT_CANDIDATES = ["cache", "small_model", "large_model"]


async def _decide_route(client: httpx.AsyncClient, agent_id: str, capability: str, candidates: list[str]) -> dict:
    """Ask Cost Optimiser to score each candidate; return the best decision.

    Degrades cleanly: if Cost Optimiser is unreachable or errors, the result is
    {"status": "unavailable", ...} and /execute still answers 200.
    """
    decisions = []
    for candidate in candidates:
        try:
            resp = await client.post(
                f"{SERVICES['cost-optimiser']}/route/decide",
                json={"agent_id": agent_id, "capability": capability, "candidate_route": candidate},
                timeout=2.0,
            )
            resp.raise_for_status()
            decisions.append(resp.json())
        except Exception as e:
            return {"status": "unavailable", "error": f"cost-optimiser: {e}", "candidates": candidates}
    best = max(decisions, key=lambda d: d.get("utility_score", float("-inf")))
    return {
        "status": "decided",
        "selected": best.get("candidate_route"),
        "utility_score": best.get("utility_score"),
        "explanation": best.get("explanation"),
        "scores": {d.get("candidate_route"): d.get("utility_score") for d in decisions},
    }


@app.post("/execute")
async def execute(agent_id: str, capability: str, payload: dict, route: str | None = None):
    # Looks the agent up in Registry, then asks Cost Optimiser which tier of
    # the RFC-0008 hierarchy should serve the call. Executing the chosen tier
    # is not wired yet: the decision is returned alongside the request.
    if route is not None and route not in ROUTES:
        raise HTTPException(status_code=422, detail=f"unknown route '{route}'; expected one of {ROUTES}")
    candidates = [route] if route else DEFAULT_CANDIDATES
    async with httpx.AsyncClient(timeout=5.0) as client:
        agent = await client.get(f"{SERVICES['registry']}/agents/{agent_id}")
        decision = await _decide_route(client, agent_id, capability, candidates)
        return {"agent": agent.json(), "capability": capability, "payload": payload, "route": decision}
