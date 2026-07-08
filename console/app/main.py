"""AEP-X Console — the LLM / machine-learning box.

A web GUI over the platform: chat requests route through the Connector Bus
(trust check -> policy check -> ML connector, per SOA-Architecture.md §3),
and uploads (files, folders, images, videos) are stored locally with their
metadata available as chat context. The GUI itself is a single static page
served from ./static — no frontend build step, consistent with the
"extremely low cost / simple to extend" positioning.
"""
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import httpx
import mimetypes
import os
import time
import uuid

app = FastAPI(title="AEP-X Console", version="0.2.0")

BUS_URL = os.getenv("CONNECTOR_BUS_URL", "http://connector-bus:8000")
REGISTRY_URL = os.getenv("REGISTRY_URL", "http://registry:8000")
TRUST_URL = os.getenv("TRUST_URL", "http://trust:8000")
GOVERNANCE_URL = os.getenv("GOVERNANCE_URL", "http://governance:8000")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/data/uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Upload metadata registry — swap for the `knowledge.*` schema before Beta
# so uploads become searchable knowledge entries.
_UPLOADS: dict[str, dict] = {}


def _kind_for(content_type: str | None) -> str:
    if not content_type:
        return "file"
    if content_type.startswith("image/"):
        return "image"
    if content_type.startswith("video/"):
        return "video"
    return "file"


@app.get("/health")
def health():
    return {"status": "ok", "service": "console", "uploads": len(_UPLOADS)}


@app.post("/api/upload")
async def upload(files: list[UploadFile] = File(...)):
    stored = []
    for f in files:
        file_id = str(uuid.uuid4())
        # Folder uploads arrive with relative paths in the filename — keep
        # the path for display but store flat under a UUID to avoid
        # traversal issues.
        safe_name = os.path.basename(f.filename or "unnamed")
        dest = os.path.join(UPLOAD_DIR, f"{file_id}_{safe_name}")
        size = 0
        with open(dest, "wb") as out:
            while chunk := await f.read(1024 * 1024):
                out.write(chunk)
                size += len(chunk)
        meta = {
            "id": file_id,
            "name": f.filename or "unnamed",
            "stored_as": os.path.basename(dest),
            "content_type": f.content_type,
            "kind": _kind_for(f.content_type),
            "size": size,
            "uploaded_at": time.time(),
        }
        _UPLOADS[file_id] = meta
        stored.append(meta)
    return {"uploaded": stored}


@app.get("/api/uploads")
def list_uploads():
    return sorted(_UPLOADS.values(), key=lambda u: u["uploaded_at"], reverse=True)


@app.get("/api/uploads/{file_id}/content")
def get_upload_content(file_id: str):
    meta = _UPLOADS.get(file_id)
    if not meta:
        raise HTTPException(404, "upload not found")
    path = os.path.join(UPLOAD_DIR, meta["stored_as"])
    media_type = meta["content_type"] or mimetypes.guess_type(meta["name"])[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=meta["name"])


class ChatIn(BaseModel):
    prompt: str
    attachment_ids: list[str] = []
    connector: str = "ml"  # any aiplatform connector from the catalogue


@app.post("/api/chat")
async def chat(msg: ChatIn):
    attachments = [_UPLOADS[a] for a in msg.attachment_ids if a in _UPLOADS]
    envelope = {
        "version": "1.0",
        "sender": "aepx://agent/console",
        "receiver": f"aepx://connector/{msg.connector}",
        "messageType": "request",
        "payload": {
            "op": "completion",
            "prompt": msg.prompt,
            "attachments": [
                {"name": a["name"], "kind": a["kind"], "content_type": a["content_type"], "size": a["size"]}
                for a in attachments
            ],
        },
        "metadata": {"source": "console"},
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{BUS_URL}/bus/route", json=envelope)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"connector bus unreachable: {e}")
    if resp.status_code != 200:
        detail = resp.json().get("detail", "denied")
        raise HTTPException(resp.status_code, detail)
    routed = resp.json()
    return {
        "reply": routed["response"].get("result", ""),
        "model": routed["response"].get("model"),
        "confidence": routed["response"].get("confidence"),
        "estimated_cost": routed["response"].get("estimated_cost"),
        # Prefer the adapter's own per-call maturity (e.g. "specialized_degraded"
        # on an Ollama fallback) over the bus's static catalogue maturity —
        # otherwise a degraded response reads as fully live to the user.
        "maturity": routed["response"].get("maturity", routed.get("maturity")),
        "connector": routed.get("connector"),
        "trust_score_at_call_time": routed.get("trust_score_at_call_time"),
        "attachment_count": len(attachments),
    }


@app.get("/api/agents")
async def list_agents_ranked():
    # Registry's own `agents.trust_score` column is a stale snapshot from
    # creation time — the real, evolving score lives in the Trust service
    # (RFC-0002 5-component formula, updated on every successful connector
    # invocation). Merge the two so the ranking reflects actual behaviour.
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            reg_resp = await client.get(f"{REGISTRY_URL}/agents")
            agents = reg_resp.json()
            enriched = []
            for a in agents:
                try:
                    trust_resp = await client.get(f"{TRUST_URL}/trust/{a['id']}")
                    trust = trust_resp.json()
                except Exception:
                    trust = {"trust_score": a.get("trust_score", 0), "level": "Unknown"}
                enriched.append({
                    "id": a["id"],
                    "name": a["name"],
                    "version": a.get("version"),
                    "trust_score": trust.get("trust_score", 0),
                    "level": trust.get("level", "Unknown"),
                    "components": {
                        k: trust[k] for k in
                        ("identity_score", "behaviour_score", "security_score", "evidence_score", "reputation_score")
                        if k in trust
                    },
                })
    except Exception:
        return []
    enriched.sort(key=lambda a: a["trust_score"], reverse=True)
    return enriched


@app.get("/api/activity")
async def recent_activity(limit: int = 30):
    # Live feed of the protocol in action — the Governance Engine's
    # unconditional audit trail (Law 8), already fed by every real Kafka
    # event (workflow.completed, connector.invoked, connector.failed,
    # safety.flagged, ...).
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{GOVERNANCE_URL}/audit", params={"limit": limit})
            return resp.json()
    except Exception:
        return []


# Serve the GUI last so /api and /health take precedence.
app.mount("/", StaticFiles(directory=os.getenv("STATIC_DIR", "static"), html=True), name="static")
