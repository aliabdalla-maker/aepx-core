from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import json
import os

from app.adapters import SPECIALIZED, StubAdapter

CATEGORY = os.getenv("CATEGORY", "messaging")
CATALOGUE_PATH = os.getenv("CATALOGUE_PATH", "/app/catalogue.json")

app = FastAPI(title=f"AEP-X Connector Service — {CATEGORY}", version="0.2.0")


def _load_my_connectors() -> dict:
    try:
        with open(CATALOGUE_PATH, encoding="utf-8") as f:
            cat = json.load(f)
        return {c["name"]: c for c in cat["connectors"] if c["category"] == CATEGORY}
    except Exception:
        # Catalogue not mounted (e.g. bare unit-test run) — specialized
        # adapters still work; stub dispatch requires the catalogue.
        return {}


MY_CONNECTORS = _load_my_connectors()


class Envelope(BaseModel):
    version: str = "1.0"
    sender: str
    receiver: str
    messageType: str = "request"
    payload: dict
    metadata: dict = {}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": f"connector-{CATEGORY}",
        "adapters": sorted(set(MY_CONNECTORS) | set(SPECIALIZED)),
        "specialized": sorted(SPECIALIZED),
    }


@app.post("/connector/execute")
def execute(envelope: Envelope):
    name = envelope.receiver.rstrip("/").split("/")[-1]
    if name in SPECIALIZED:
        return SPECIALIZED[name].execute(envelope.payload)
    if name in MY_CONNECTORS:
        return StubAdapter(name, CATEGORY).execute(envelope.payload)
    raise HTTPException(404, f"connector '{name}' is not registered in category '{CATEGORY}'")
