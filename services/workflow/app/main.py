from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import httpx
import json
import uuid
import time
import os

app = FastAPI(title="AEP-X Workflow Engine", version="0.2.0")
REGISTRY_URL = os.getenv("REGISTRY_URL", "http://registry:8000")
MEMORY_URL = os.getenv("MEMORY_URL", "http://memory:8000")
_WORKFLOWS: dict[str, dict] = {}
_MAX_STEPS = 20

try:
    from kafka import KafkaProducer
    _KAFKA_IMPORTABLE = True
except Exception:
    _KAFKA_IMPORTABLE = False
producer = None

def _get_producer():
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

class StepIn(BaseModel):
    capability: str = Field(min_length=1, max_length=128)
    agent_id: str = Field(min_length=1, max_length=128)
    risk_level: str = "S0"

class WorkflowIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    steps: list[StepIn] = Field(min_length=1, max_length=_MAX_STEPS)

@app.get("/health")
def health():
    return {"status": "ok", "service": "workflow"}

@app.post("/workflows")
def create_workflow(w: WorkflowIn):
    # Only low-risk, read-only metadata lookup is implemented. High-risk
    # execution and arbitrary tool invocation are deliberately not enabled.
    for step in w.steps:
        if step.risk_level not in ("S0", "S1", "S2"):
            raise HTTPException(status_code=403, detail="high-risk or invalid step requires governed approval; execution disabled")
    wf_id = str(uuid.uuid4())
    _WORKFLOWS[wf_id] = {"id": wf_id, "status": "CREATED", **w.model_dump()}
    return _WORKFLOWS[wf_id]

@app.get("/workflows/{wf_id}")
def get_workflow(wf_id: str):
    wf = _WORKFLOWS.get(wf_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    return wf

@app.post("/workflows/{wf_id}/execute")
async def execute_workflow(wf_id: str):
    wf = _WORKFLOWS.get(wf_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    if wf["status"] != "CREATED":
        raise HTTPException(status_code=409, detail="workflow already attempted; duplicate execution blocked")
    if any(step["risk_level"] not in ("S0", "S1", "S2") for step in wf["steps"]):
        raise HTTPException(status_code=403, detail="workflow contains unapproved high-risk step")
    wf["status"] = "RUNNING"
    results = []
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            payload = {}
            for step in wf["steps"]:
                agent = await client.get(f"{REGISTRY_URL}/agents/{step['agent_id']}")
                agent.raise_for_status()
                result = {"capability": step["capability"], "agent": agent.json(), "input": payload}
                results.append(result)
                payload = result
    except (httpx.HTTPError, ValueError) as exc:
        wf["status"] = "FAILED"
        wf["error_type"] = type(exc).__name__
        raise HTTPException(status_code=502, detail="registry lookup failed; workflow marked FAILED") from exc
    wf["status"], wf["results"] = "COMPLETED", results
    event = {"workflow_id": wf_id, "status": "COMPLETED", "step_count": len(results), "ts": time.time()}
    p = _get_producer()
    if p:
        try:
            p.send("workflow.completed", event)
        except Exception:
            wf["event_delivery"] = "unconfirmed"
    else:
        wf["event_delivery"] = "unconfirmed"
    return wf
