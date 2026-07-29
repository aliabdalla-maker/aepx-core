from fastapi import FastAPI
from pydantic import BaseModel
import time

app = FastAPI(title="AEP-X Memory Service", version="0.0.1")
_SESSION_MEMORY: dict[str, list[dict]] = {}


class MemoryWrite(BaseModel):
    agent_id: str
    content: dict


@app.get("/health")
def health():
    return {"status": "ok", "service": "memory"}


@app.post("/memory/session")
def write_session(m: MemoryWrite):
    _SESSION_MEMORY.setdefault(m.agent_id, []).append({**m.content, "ts": time.time()})
    return {"stored": True}


@app.get("/memory/session/{agent_id}")
def read_session(agent_id: str):
    return _SESSION_MEMORY.get(agent_id, [])
