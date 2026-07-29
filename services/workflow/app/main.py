from fastapi import FastAPI
from pydantic import BaseModel
import httpx
import json
import uuid
import time
import os

app = FastAPI(title="AEP-X Workflow Engine", version="0.1.0")
REGISTRY_URL = os.getenv("REGISTRY_URL", "http://registry:8000")
MEMORY_URL = os.getenv("MEMORY_URL", "http://memory:8000")
_WORKFLOWS: dict[str, dict] = {}

try:
    from kafka import KafkaProducer
    _KAFKA_IMPORTABLE = True
except Exception:
    _KAFKA_IMPORTABLE = False

producer = None


def _get_producer():
    # Lazy + retried: a producer created once at import stays None forever
    # if the broker loses the compose startup race, silently dropping every
    # workflow.completed event. Reconnecting per call fixes that; the
    # instance is cached after the first success.
    global producer
    if producer is None and _KAFKA_IMPORTABLE:
        try:
            producer = KafkaProducer(
                bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP", "kafka:9092"),
                value_serializer=lambda v: json.dumps(v).encode(),
            )
        except Exception:
            producer = None
    return producer


class WorkflowIn(BaseModel):
    name: str
    steps: list[dict]  # [{"capability": "...", "agent_id": "..."}]


@app.get("/health")
def health():
    return {"status": "ok", "service": "workflow"}


@app.post("/workflows")
def create_workflow(w: WorkflowIn):
    wf_id = str(uuid.uuid4())
    _WORKFLOWS[wf_id] = {"id": wf_id, "status": "CREATED", **w.model_dump()}
    return _WORKFLOWS[wf_id]


@app.post("/workflows/{wf_id}/execute")
async def execute_workflow(wf_id: str):
    wf = _WORKFLOWS[wf_id]
    wf["status"] = "RUNNING"
    results = []
    async with httpx.AsyncClient(timeout=5.0) as client:
        payload = {}
        for step in wf["steps"]:
            agent = await client.get(f"{REGISTRY_URL}/agents/{step['agent_id']}")
            result = {"capability": step["capability"], "agent": agent.json(), "input": payload}
            results.append(result)
            payload = result  # thread output of step N into step N+1
    wf["status"], wf["results"] = "COMPLETED", results
    event = {
        "workflow_id": wf_id, "status": "COMPLETED",
        "step_count": len(results), "ts": time.time(),
    }
    p = _get_producer()
    if p:
        p.send("workflow.completed", event)
    return wf
