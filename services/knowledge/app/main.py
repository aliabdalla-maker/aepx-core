from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uuid
import time

app = FastAPI(title="AEP-X Knowledge Service", version="0.1.0")


class KnowledgeIn(BaseModel):
    title: str
    content: str
    source: str
    confidence: float = 0.8


class Knowledge(KnowledgeIn):
    id: str
    trust_score: int = 50
    created_at: float


_KNOWLEDGE: dict[str, Knowledge] = {}


@app.get("/health")
def health():
    return {"status": "ok", "service": "knowledge"}


@app.post("/knowledge", response_model=Knowledge)
def create_knowledge(payload: KnowledgeIn):
    kid = str(uuid.uuid4())
    entry = Knowledge(id=kid, created_at=time.time(), **payload.model_dump())
    _KNOWLEDGE[kid] = entry
    return entry


@app.get("/knowledge/{knowledge_id}", response_model=Knowledge)
def get_knowledge(knowledge_id: str):
    if knowledge_id not in _KNOWLEDGE:
        raise HTTPException(404, "not found")
    return _KNOWLEDGE[knowledge_id]


@app.post("/knowledge/search")
def search_knowledge(query: str, limit: int = 5):
    # Scaffold: naive substring match. Swap for pgvector cosine similarity
    # before the Alpha Gate — flag explicitly in the PR (see Instructional
    # Manual §3.3 convention for "scaffold, not final" call-outs).
    hits = [k for k in _KNOWLEDGE.values() if query.lower() in k.content.lower()]
    return {"query": query, "results": hits[:limit]}
