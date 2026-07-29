from fastapi import FastAPI
from pydantic import BaseModel
import threading
import time

app = FastAPI(title="AEP-X ML Integration Service", version="0.1.0")

# In-memory model registry metadata — swap for PostgreSQL `ml.*` schema
# before Beta (docs/Microservices-Architecture-v2.md §3).
_MODELS: dict[str, dict] = {
    "cost_prediction": {"version": "0.1.0", "trained_at": None, "sample_count": 0},
    "demand_prediction": {"version": "0.1.0", "trained_at": None, "sample_count": 0},
    "workflow_recommendation": {"version": "0.1.0", "trained_at": None, "sample_count": 0},
}


class PredictIn(BaseModel):
    model: str  # one of _MODELS keys
    features: dict


class RecommendIn(BaseModel):
    context: dict


@app.get("/health")
def health():
    return {"status": "ok", "service": "ml-integration"}


@app.post("/predict")
def predict(p: PredictIn):
    if p.model not in _MODELS:
        return {"error": f"unknown model {p.model}"}
    # Scaffold: deterministic placeholder prediction. Real models trained
    # from workflow.completed / safety.flagged / verification.completed
    # feedback (Law 9, the learning loop) — see consume_feedback_events below.
    return {"model": p.model, "prediction": 0.5, "confidence": 0.5, "model_version": _MODELS[p.model]["version"]}


@app.post("/recommend")
def recommend(r: RecommendIn):
    # Scaffold: recommends the cheapest route by default until real
    # recommendation models exist — consistent with cache-first economics
    # (RFC-0008) rather than an arbitrary default.
    return {"recommended_route": "cache", "reason": "no trained model yet — defaulting to cheapest safe route"}


@app.get("/models")
def list_models():
    return _MODELS


def consume_feedback_events():
    # Scaffold placeholder for the Kafka consumer thread subscribing to
    # workflow.completed, safety.flagged, and verification.completed — the
    # feedback loop this service exists to close (Law 9, Learning).
    # Mirrors Safety Engine's consumer-thread pattern (Microservices Guide
    # §5.3). Not started against a real broker in this scaffold.
    while False:
        time.sleep(1)


threading.Thread(target=consume_feedback_events, daemon=True).start()
