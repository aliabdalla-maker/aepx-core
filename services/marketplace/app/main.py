"""AEP-X Marketplace Engine.

Publish and discover platform assets (agents, workflows, plugins, knowledge
packs). The point of interest is the **governed publish gate**: a listing
can only go from draft to published if, at publish time, the publisher's
trust score clears the bar (Law 2) AND Governance's policy allows the
listing's risk level (Law 6/8). Trust-before-execution applied to the act of
publishing — unvetted assets can't reach the catalogue.

Fail-closed on the gate: if Trust or Governance can't be reached, the
listing is NOT published (unlike the rest of the platform's read paths,
which fail-open/degrade — for a publish decision the safe default is to
withhold). The store is in-memory (reference implementation); the durable
record is the audit trail Governance keeps when the gate runs.
"""
import os
import time
import uuid

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="AEP-X Marketplace Engine", version="0.1.0")

TRUST_URL = os.getenv("TRUST_URL", "http://trust:8000")
GOVERNANCE_URL = os.getenv("GOVERNANCE_URL", "http://governance:8000")
MIN_PUBLISH_TRUST = int(os.getenv("MARKETPLACE_MIN_TRUST", "60"))
ASSET_TYPES = {"agent", "workflow", "plugin", "knowledge_pack", "model"}

_LISTINGS: dict[str, dict] = {}


class ListingIn(BaseModel):
    name: str
    asset_type: str = "agent"
    publisher: str = "aepx://agent/anonymous"
    risk_level: str = "S2"
    description: str = ""


@app.get("/health")
def health():
    return {"status": "ok", "service": "marketplace", "listings": len(_LISTINGS)}


@app.post("/marketplace/listings")
def create_listing(body: ListingIn):
    if body.asset_type not in ASSET_TYPES:
        raise HTTPException(400, f"asset_type must be one of {sorted(ASSET_TYPES)}")
    listing_id = str(uuid.uuid4())
    _LISTINGS[listing_id] = {
        "id": listing_id,
        "name": body.name,
        "asset_type": body.asset_type,
        "publisher": body.publisher,
        "risk_level": body.risk_level,
        "description": body.description,
        "status": "draft",
        "created_at": time.time(),
    }
    return _LISTINGS[listing_id]


@app.get("/marketplace/listings")
def list_listings(status: str | None = None):
    items = list(_LISTINGS.values())
    if status:
        items = [x for x in items if x["status"] == status]
    return items


@app.get("/marketplace/listings/{listing_id}")
def get_listing(listing_id: str):
    if listing_id not in _LISTINGS:
        raise HTTPException(404, "listing not found")
    return _LISTINGS[listing_id]


@app.post("/marketplace/listings/{listing_id}/publish")
def publish_listing(listing_id: str):
    """Run the governed publish gate. Trust >= threshold AND policy allow, or
    the listing stays unpublished with a reason. Fail-closed if either check
    is unreachable."""
    if listing_id not in _LISTINGS:
        raise HTTPException(404, "listing not found")
    listing = _LISTINGS[listing_id]

    trust_score, trust_reason = _check_trust(listing["publisher"])
    if trust_score is None:
        return _deny(listing, f"trust check unavailable ({trust_reason}) — fail-closed")
    if trust_score < MIN_PUBLISH_TRUST:
        return _deny(listing, f"publisher trust {trust_score} < required {MIN_PUBLISH_TRUST}")

    allowed, policy_reason = _check_policy(listing["risk_level"])
    if allowed is None:
        return _deny(listing, f"policy check unavailable ({policy_reason}) — fail-closed")
    if not allowed:
        return _deny(listing, f"policy denied risk level {listing['risk_level']} ({policy_reason})")

    listing["status"] = "published"
    listing["published_at"] = time.time()
    listing["publish_trust_score"] = trust_score
    return listing


def _deny(listing: dict, reason: str) -> dict:
    listing["status"] = "review"
    listing["last_denied_reason"] = reason
    return {**listing, "published": False, "reason": reason}


def _check_trust(entity_id: str):
    try:
        r = httpx.get(f"{TRUST_URL}/trust/{entity_id}", timeout=5.0)
        r.raise_for_status()
        return int(r.json().get("trust_score", 0)), None
    except Exception as e:
        return None, type(e).__name__


def _check_policy(risk_level: str):
    try:
        r = httpx.post(f"{GOVERNANCE_URL}/policy/evaluate", params={"risk_level": risk_level}, timeout=5.0)
        r.raise_for_status()
        return bool(r.json().get("allowed")), None
    except Exception as e:
        return None, type(e).__name__
