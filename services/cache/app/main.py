from fastapi import FastAPI, HTTPException
import redis
import os
import json

app = FastAPI(title="AEP-X Cache Service (L0-L5)", version="0.2.0")
r = redis.Redis(host=os.getenv("REDIS_HOST", "redis"), port=6379, decode_responses=True)

# Canonical cache layers — RFC-0005, resolved per ADLC Plan §15.3 and
# reaffirmed by the full-source read (rfcs/RFC-0005-memory-cache.md).
# Supersedes the original Instructional Manual §3.5 L1-only MVP stub.
CACHE_LAYERS = {
    "L0": 300,       # Prompt — 5 minutes
    "L1": 3600,      # Session — 1 hour (the original Instructional Manual scope)
    "L2": 86400,     # Agent — 24 hours
    "L3": 604800,    # Workflow — 7 days
    "L4": 2592000,   # Organisation — 30 days
    # L5 Federation has no fixed TTL — Governance Engine policy decides
    # per call whether cross-organisation reuse is permitted at all.
}


@app.get("/health")
def health():
    return {"status": "ok", "service": "cache", "redis": r.ping(), "layers": list(CACHE_LAYERS) + ["L5"]}


@app.get("/cache/{layer}/{key}")
def get_cache(layer: str, key: str):
    if layer not in CACHE_LAYERS and layer != "L5":
        raise HTTPException(400, f"unknown layer {layer}")
    val = r.get(f"{layer}:{key}")
    return {"layer": layer, "key": key, "value": json.loads(val) if val else None, "hit": val is not None}


@app.post("/cache/{layer}/{key}")
def set_cache(layer: str, key: str, value: dict, l5_policy_allowed: bool = False):
    if layer == "L5":
        if not l5_policy_allowed:
            raise HTTPException(403, "L5_policy_denied: caller must confirm Governance Engine policy allows federation-tier caching")
        r.set(f"{layer}:{key}", json.dumps(value))  # no TTL — governed by explicit invalidation
        return {"stored": True, "layer": layer, "ttl": None}
    if layer not in CACHE_LAYERS:
        raise HTTPException(400, f"unknown layer {layer}")
    ttl = CACHE_LAYERS[layer]
    r.set(f"{layer}:{key}", json.dumps(value), ex=ttl)
    return {"stored": True, "layer": layer, "ttl": ttl}


# Backwards-compatible single-layer alias for the original Instructional
# Manual §3.5 /cache/{key} shape, defaulting to L1 Session (its original
# scope), so anything built against the v0.0.1 stub keeps working.
@app.get("/cache/{key}")
def get_cache_legacy(key: str):
    return get_cache("L1", key)


@app.post("/cache/{key}")
def set_cache_legacy(key: str, value: dict, ttl: int = 3600):
    r.set(f"L1:{key}", json.dumps(value), ex=ttl)
    return {"stored": True, "ttl": ttl}
