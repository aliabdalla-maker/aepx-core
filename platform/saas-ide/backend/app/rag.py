"""Tenant-scoped pgvector retrieval with an explicitly configured embedding provider."""
import os
import uuid
from sqlalchemy import text
from sqlalchemy.orm import Session
from .main import Principal, project_or_404

EMBEDDING_DIMENSIONS = 1536

def embed(text_value: str) -> list[float]:
    if os.getenv("IDE_EXTERNAL_EXECUTION_ENABLED") != "true" or os.getenv("IDE_RAG_EMBEDDING_ENABLED") != "true":
        raise PermissionError("External embeddings disabled")
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Embedding API key missing")
    from openai import OpenAI
    with OpenAI(timeout=20, max_retries=0) as client:
        result = client.embeddings.create(model=os.getenv("IDE_EMBEDDING_MODEL", "text-embedding-3-small"),
                                          input=text_value[:8000], dimensions=EMBEDDING_DIMENSIONS)
        vector = result.data[0].embedding
    if len(vector) != EMBEDDING_DIMENSIONS:
        raise ValueError("Embedding dimension mismatch")
    return vector

def vector_literal(values: list[float]) -> str:
    if len(values) != EMBEDDING_DIMENSIONS:
        raise ValueError("Embedding dimension mismatch")
    import math
    if not all(math.isfinite(v) for v in values):
        raise ValueError("Non-finite embedding")
    return "[" + ",".join(str(float(x)) for x in values) + "]"

def index_document(db: Session, p: Principal, project_id: str, document_id: str, content: str) -> int:
    if p.role not in ("owner", "admin", "editor"):
        raise PermissionError("Read-only membership")
    project_or_404(db, p.tenant_id, project_id)
    owned = db.execute(text("""SELECT id FROM ide_knowledge_documents
       WHERE id=:doc AND tenant_id=:tenant AND project_id=:project"""),
       {"doc": document_id, "tenant": p.tenant_id, "project": project_id}).first()
    if owned is None:
        raise LookupError("Document not found")
    chunks = [content[i:i+1500] for i in range(0, min(len(content), 12000), 1500)]
    vectors = [vector_literal(embed(chunk)) for chunk in chunks]
    db.execute(text("""DELETE FROM ide_knowledge_vectors
        WHERE tenant_id=:tenant AND project_id=:project AND document_id=:doc"""),
        {"tenant": p.tenant_id, "project": project_id, "doc": document_id})
    for chunk, vector in zip(chunks, vectors):
        db.execute(text("""INSERT INTO ide_knowledge_vectors
            (id,tenant_id,project_id,document_id,chunk,embedding)
            VALUES (:id,:tenant,:project,:doc,:chunk,CAST(:vector AS vector))"""),
            {"id": str(uuid.uuid4()), "tenant": p.tenant_id, "project": project_id,
             "doc": document_id, "chunk": chunk, "vector": vector})
    db.commit()
    return len(chunks)

def search_vectors(db: Session, p: Principal, project_id: str, query: str) -> list[dict]:
    project_or_404(db, p.tenant_id, project_id)
    vector = vector_literal(embed(query))
    rows = db.execute(text("""SELECT document_id,chunk,
            1 - (embedding <=> CAST(:vector AS vector)) AS score
            FROM ide_knowledge_vectors
            WHERE tenant_id=:tenant AND project_id=:project
            ORDER BY embedding <=> CAST(:vector AS vector) LIMIT 5"""),
            {"vector": vector, "tenant": p.tenant_id, "project": project_id}).all()
    return [{"document_id": row.document_id, "excerpt": row.chunk, "score": float(row.score)}
            for row in rows]
