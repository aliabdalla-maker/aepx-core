from fastapi import FastAPI
from pydantic import BaseModel
import json
import os
import threading
import time

app = FastAPI(title="AEP-X Safety Engine", version="0.1.0")

try:
    from kafka import KafkaProducer, KafkaConsumer
    _KAFKA_AVAILABLE = True
except Exception:
    _KAFKA_AVAILABLE = False

_producer = None


def _get_producer():
    # Lazy + retried — see services/workflow/app/main.py for why.
    global _producer
    if _producer is None and _KAFKA_AVAILABLE:
        try:
            _producer = KafkaProducer(
                bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP", "kafka:9092"),
                value_serializer=lambda v: json.dumps(v).encode(),
            )
        except Exception:
            _producer = None
    return _producer


class ValidateIn(BaseModel):
    answer: str
    evidence: list[str] = []


CONFIDENCE_BANDS = [(95, "Verified"), (80, "High"), (60, "Medium"), (0, "Unverified")]


def band_for(evidence_count: int) -> str:
    score = min(100, evidence_count * 35)
    for threshold, label in CONFIDENCE_BANDS:
        if score >= threshold:
            return label
    return "Unverified"


@app.get("/health")
def health():
    return {"status": "ok", "service": "safety"}


@app.post("/safety/validate")
def validate(v: ValidateIn):
    verification_status = band_for(len(v.evidence))
    p = _get_producer()
    if verification_status == "Unverified" and p:
        p.send("safety.flagged", {"reason": "no_evidence", "answer": v.answer[:200]})
    return {"answer": v.answer, "confidence": len(v.evidence) * 0.35,
            "evidence": v.evidence, "verification_status": verification_status}


def consume_workflow_events():
    # Reconnect loop is load-bearing — see governance/app/main.py for why.
    if not _KAFKA_AVAILABLE:
        return
    while True:
        try:
            consumer = KafkaConsumer("workflow.completed", bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP", "kafka:9092"),
                                      value_deserializer=lambda v: json.loads(v.decode()))
            for msg in consumer:
                event = msg.value
                # Alpha-stage rule: any workflow with zero result steps is flagged for review
                p = _get_producer()
                if event.get("step_count", 0) == 0 and p:
                    p.send("safety.flagged", {"reason": "empty_workflow", **event})
        except Exception:
            time.sleep(5)


threading.Thread(target=consume_workflow_events, daemon=True).start()
