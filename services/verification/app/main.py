from fastapi import FastAPI
from pydantic import BaseModel
import json
import threading

app = FastAPI(title="AEP-X Verification Engine", version="0.1.0")

# CONFIDENCE_BANDS use the source's own labels (GREEN/AMBER/RED/GREY), not
# the Safety Engine's Verified/High/Medium/Unverified labels — the two
# services answer different questions (see docs/Microservices-Architecture-v2.md
# §6). Do not merge these label sets.
CONFIDENCE_BANDS = [(95, "GREEN"), (80, "AMBER"), (60, "RED"), (0, "GREY")]


class Claim(BaseModel):
    text: str
    source_ids: list[str] = []


class VerifyIn(BaseModel):
    workflow_id: str
    claims: list[Claim]


def truth_score(claim: Claim) -> float:
    # Scaffold: truth score is a function of how much evidence backs the
    # claim. Real implementation correlates against Knowledge Service
    # (evidence quality + source trust + diversity + consistency + recency,
    # per RFC-0007) before the Alpha Gate.
    return min(100.0, len(claim.source_ids) * 35.0)


def band_for(score: float) -> str:
    for threshold, label in CONFIDENCE_BANDS:
        if score >= threshold:
            return label
    return "GREY"


@app.get("/health")
def health():
    return {"status": "ok", "service": "verification"}


@app.post("/verify")
def verify(v: VerifyIn):
    results = []
    for claim in v.claims:
        score = truth_score(claim)
        results.append(
            {
                "claim": claim.text,
                "truth_score": score,
                "confidence_band": band_for(score),
                "citations": claim.source_ids,
            }
        )
    truth_avg = sum(r["truth_score"] for r in results) / len(results) if results else 0.0
    event = {
        "workflow_id": v.workflow_id,
        "claim_count": len(results),
        "truth_score": truth_avg,
        "confidence_band": band_for(truth_avg),
        "citations": [c for r in results for c in r["citations"]],
    }
    _publish("verification.completed", event)
    return {"workflow_id": v.workflow_id, "results": results, "summary": event}


def _publish(topic: str, payload: dict):
    # Scaffold: swap for a real KafkaProducer once this service is wired
    # into the shared bus (see Microservices Guide §5.2 for the established
    # kafka-python pattern used by Workflow Engine).
    print(f"[verification] would publish to {topic}: {json.dumps(payload)}")


def consume_workflow_events():
    # Scaffold placeholder for the KafkaConsumer thread that reacts to
    # workflow.completed, mirroring Safety Engine's pattern
    # (Microservices Guide §5.3). Not started by default in this scaffold.
    pass


threading.Thread(target=consume_workflow_events, daemon=True).start()
