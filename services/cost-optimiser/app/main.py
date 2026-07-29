from fastapi import FastAPI
from pydantic import BaseModel
import httpx
import os

app = FastAPI(title="AEP-X Cost Optimiser Service", version="0.1.0")

TRUST_URL = os.getenv("TRUST_URL", "http://trust:8000")

# Utility Score weights, per the source's own formula (repeated consistently
# across passes): Accuracy + Trust + Compliance + Performance - Cost -
# Latency - Energy - Risk. Weights below are a starting point — tune with
# pilot data, don't treat as a platform guarantee (ADLC Plan §15.4).
WEIGHTS = {
    "accuracy": 0.25,
    "trust": 0.20,
    "compliance": 0.15,
    "performance": 0.10,
    "cost": -0.15,
    "latency": -0.05,
    "energy": -0.05,
    "risk": -0.05,
}

ROUTES = ["cache", "memory", "knowledge", "workflow", "tool", "small_model", "medium_model", "large_model", "human"]


class RouteRequest(BaseModel):
    agent_id: str
    capability: str
    candidate_route: str  # one of ROUTES
    estimated_cost: float = 0.0
    estimated_latency_ms: float = 0.0
    estimated_energy: float = 0.0


def utility_score(trust_score: int, request: RouteRequest) -> float:
    accuracy = 0.9  # scaffold placeholder — wire to Verification Engine's truth_score once available
    compliance = 1.0 if request.candidate_route not in ("large_model",) else 0.9
    performance = 1.0 - min(request.estimated_latency_ms / 1000, 1.0)
    risk = 0.1 if request.candidate_route == "human" else 0.0
    return (
        WEIGHTS["accuracy"] * accuracy
        + WEIGHTS["trust"] * (trust_score / 100)
        + WEIGHTS["compliance"] * compliance
        + WEIGHTS["performance"] * performance
        + WEIGHTS["cost"] * request.estimated_cost
        + WEIGHTS["latency"] * (request.estimated_latency_ms / 1000)
        + WEIGHTS["energy"] * request.estimated_energy
        + WEIGHTS["risk"] * risk
    )


@app.get("/health")
def health():
    return {"status": "ok", "service": "cost-optimiser"}


@app.post("/route/decide")
async def decide(request: RouteRequest):
    async with httpx.AsyncClient(timeout=2.0) as client:
        trust = (await client.get(f"{TRUST_URL}/trust/{request.agent_id}")).json()
    score = utility_score(trust.get("trust_score", 50), request)
    return {
        "agent_id": request.agent_id,
        "candidate_route": request.candidate_route,
        "utility_score": score,
        "breakdown": WEIGHTS,
        "explanation": (
            f"Routing to '{request.candidate_route}' scored {score:.3f}. "
            "Routing chooses highest utility, not highest intelligence "
            "(Law 5, Reuse Before Computation)."
        ),
    }
