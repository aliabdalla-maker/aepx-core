"""AEP-X Conformance service — the testing platform (RFC-0007).

Runs the SDK's conformance suite (aepx.conformance) against any live
AEP-X deployment — this cluster by default, or any target the caller
points it at — and keeps the last runs in memory for the GUI.
"""
import itertools
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from aepx import AepxClient
from aepx.conformance import CHECKS, run_conformance

app = FastAPI(title="AEP-X Conformance — testing platform", version="0.1.0")

# In-cluster defaults — override per-run via the request body, or per-
# deployment via env (same pattern as every other service's *_URL vars).
DEFAULT_TARGET = {
    "gateway_url": os.getenv("GATEWAY_URL", "http://gateway:8000"),
    "identity_url": os.getenv("IDENTITY_URL", "http://identity:8000"),
    "trust_url": os.getenv("TRUST_URL", "http://trust:8000"),
    "registry_url": os.getenv("REGISTRY_URL", "http://registry:8000"),
    "governance_url": os.getenv("GOVERNANCE_URL", "http://governance:8000"),
    "bus_url": os.getenv("CONNECTOR_BUS_URL", "http://connector-bus:8000"),
}

_RUNS: list[dict] = []  # ring buffer, newest last
_MAX_RUNS = 50
_run_ids = itertools.count(1)


class Target(BaseModel):
    gateway_url: str | None = None
    identity_url: str | None = None
    trust_url: str | None = None
    registry_url: str | None = None
    governance_url: str | None = None
    bus_url: str | None = None


class RunRequest(BaseModel):
    target: Target | None = None
    checks: list[str] | None = None


@app.get("/health")
def health():
    return {"status": "ok", "service": "conformance", "checks_available": len(CHECKS), "runs_kept": len(_RUNS)}


@app.get("/checks")
def list_checks():
    return [{"id": c.id, "rfc": c.rfc, "title": c.title} for c in CHECKS]


@app.post("/runs")
def create_run(req: RunRequest | None = None):
    req = req or RunRequest()
    overrides = {k: v for k, v in (req.target.model_dump() if req.target else {}).items() if v}
    client = AepxClient(**{**DEFAULT_TARGET, **overrides}, timeout=15.0)
    report = run_conformance(client, ids=req.checks)
    entry = {"run_id": next(_run_ids), **report.to_dict()}
    _RUNS.append(entry)
    del _RUNS[:-_MAX_RUNS]
    return entry


@app.get("/runs")
def list_runs():
    return [{k: run[k] for k in ("run_id", "passed", "failed", "skipped", "conformant", "duration_seconds")}
            for run in reversed(_RUNS)]


@app.get("/runs/{run_id}")
def get_run(run_id: int):
    for run in _RUNS:
        if run["run_id"] == run_id:
            return run
    raise HTTPException(404, f"run {run_id} not found (only the last {_MAX_RUNS} are kept)")


_STATIC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.isdir(_STATIC):
    @app.get("/")
    def index():
        return FileResponse(os.path.join(_STATIC, "index.html"))

    app.mount("/static", StaticFiles(directory=_STATIC), name="static")
