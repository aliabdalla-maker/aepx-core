from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import json
import os

from app.adapters import SPECIALIZED, StubAdapter
from app.domains import DOMAIN_REGISTRY, connector_domains, get_domain

CATEGORY = os.getenv("CATEGORY", "enterprise")
CATALOGUE_PATH = os.getenv("CATALOGUE_PATH", "/app/catalogue.json")

app = FastAPI(title=f"AEP-X Connector Service — {CATEGORY}", version="0.3.0")


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
    metadata: dict = Field(default_factory=dict)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": f"connector-{CATEGORY}",
        "adapters": sorted(set(MY_CONNECTORS) | set(SPECIALIZED)),
        "specialized": sorted(SPECIALIZED),
        "domains": sorted(DOMAIN_REGISTRY),
    }


@app.get("/domains")
def list_domains():
    return {"domains": [DOMAIN_REGISTRY[name].as_dict() for name in sorted(DOMAIN_REGISTRY)]}


@app.get("/domains/{domain_name}")
def domain_detail(domain_name: str):
    domain = get_domain(domain_name)
    if not domain:
        raise HTTPException(404, f"enterprise domain '{domain_name}' is not registered")
    return domain.as_dict()


@app.get("/domains/{domain_name}/connectors")
def domain_connectors(domain_name: str):
    domain = get_domain(domain_name)
    if not domain:
        raise HTTPException(404, f"enterprise domain '{domain_name}' is not registered")
    available = sorted(name for name in domain.connectors if name in MY_CONNECTORS or name in SPECIALIZED)
    return {
        "domain": domain.name,
        "connectors": available,
        "unavailable": sorted(set(domain.connectors) - set(available)),
    }


@app.post("/connector/execute")
def execute(envelope: Envelope):
    name = envelope.receiver.rstrip("/").split("/")[-1]

    # A caller may bind a request to a first-class enterprise domain.  This
    # prevents accidental cross-domain routing while preserving backwards
    # compatibility for existing envelopes that omit metadata.domain.
    requested_domain = envelope.metadata.get("domain")
    if requested_domain:
        domain = get_domain(str(requested_domain))
        if not domain:
            raise HTTPException(400, f"enterprise domain '{requested_domain}' is not registered")
        if name not in domain.connectors:
            raise HTTPException(
                400,
                f"connector '{name}' is not approved for enterprise domain '{domain.name}'",
            )

    if name in SPECIALIZED:
        result = SPECIALIZED[name].execute(envelope.payload)
    elif name in MY_CONNECTORS:
        result = StubAdapter(name, CATEGORY).execute(envelope.payload)
    else:
        raise HTTPException(404, f"connector '{name}' is not registered in category '{CATEGORY}'")

    result["domains"] = connector_domains(name)
    if requested_domain:
        result["domain"] = str(requested_domain).lower()
    return result
