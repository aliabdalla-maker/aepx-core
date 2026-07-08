from fastapi import FastAPI
import httpx
import redis
import os
import json

app = FastAPI(title="AEP-X Discovery Service", version="0.1.0")
r = redis.Redis(host=os.getenv("REDIS_HOST", "redis"), decode_responses=True)
REGISTRY_URL = os.getenv("REGISTRY_URL", "http://registry:8000")
TRUST_URL = os.getenv("TRUST_URL", "http://trust:8000")


@app.get("/health")
def health():
    return {"status": "ok", "service": "discovery"}


def score(agent: dict, trust: dict) -> float:
    capability_match = agent.get("confidence", 0.8)
    trust_score = trust.get("trust_score", 50) / 100
    availability = 1.0  # placeholder until health-aggregation feeds this
    latency_penalty = agent.get("latency_ms", 50) / 1000
    cost_penalty = agent.get("cost", 0.0)
    return (0.40 * capability_match + 0.25 * trust_score + 0.15 * availability
            - 0.10 * latency_penalty - 0.10 * cost_penalty)


@app.get("/discover")
async def discover(capability: str):
    cache_key = f"discover:{capability}"
    cached = r.get(cache_key)
    if cached:
        return {"results": json.loads(cached), "cache_hit": True}
    async with httpx.AsyncClient(timeout=3.0) as client:
        agents = (await client.get(f"{REGISTRY_URL}/agents")).json()
        ranked = []
        for agent in agents:
            trust = (await client.get(f"{TRUST_URL}/trust/{agent['id']}")).json()
            ranked.append({**agent, "score": score(agent, trust)})
    ranked.sort(key=lambda a: a["score"], reverse=True)
    r.set(cache_key, json.dumps(ranked), ex=30)
    return {"results": ranked, "cache_hit": False}
