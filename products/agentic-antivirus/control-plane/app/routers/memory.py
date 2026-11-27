"""Agent memory and access-controlled retrieval (AGT-03, AGT-04).

Memory = tenant-scoped notes, findings, decisions and runbooks that investigations and assistants can retrieve with
source attribution. Rules enforced here and in migration 005:
- tenant separation: RLS on aav.memory_items; every query runs in the caller's tenant transaction
- access control: each item names a required permission; retrieval only returns items the caller's roles allow
- provenance: source_kind/source_ref/created_by/created_at on every version, returned with every passage
- versioning: an update writes version n+1 and supersedes n; history stays readable
- consent and retention: personal data needs a consent basis; retain_until (default from the tenant's
  privacy.memory_retention_days setting, else 365 days) is applied by aav.apply_memory_retention(); DELETE erases
  every version (right to erasure) and is audited
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from app import audit, db, rbac
from app.deps import Principal, need

router = APIRouter(prefix="/v1/memory", tags=["memory"])
KNOWN_PERMISSIONS = set().union(*rbac.PERMISSIONS.values())
DEFAULT_RETENTION_DAYS = 365


class MemoryIn(BaseModel):
    kind: str = Field(pattern="^(incident_note|runbook|finding|decision|reference)$")
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=20000)
    source_kind: str = Field(pattern="^(incident|alert|investigation|file|user|external)$")
    source_ref: str = Field(default="", max_length=500)
    required_permission: str = "incidents.read"
    contains_personal_data: bool = False
    consent_basis: str | None = Field(default=None, max_length=200)
    retain_days: int | None = Field(default=None, ge=1, le=3650)

    @model_validator(mode="after")
    def _rules(self):
        if self.required_permission not in KNOWN_PERMISSIONS:
            raise ValueError(f"unknown permission {self.required_permission}")
        if self.contains_personal_data and not self.consent_basis:
            raise ValueError("personal data needs a consent_basis (e.g. legitimate_interest_security, consent)")
        return self


class RetrieveIn(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    k: int = Field(default=5, ge=1, le=50)
    kinds: list[str] | None = None


def _retain_until(cur, days: int | None) -> datetime:
    if days is None:
        cur.execute("SELECT (value #>> '{}')::int AS d FROM aav.settings WHERE category = 'privacy' "
                    "AND key = 'memory_retention_days'")
        row = cur.fetchone()
        days = row["d"] if row and row["d"] else DEFAULT_RETENTION_DAYS
    return datetime.now(timezone.utc) + timedelta(days=days)


def _allowed_perms(p: Principal) -> list[str]:
    return sorted(perm for perm in KNOWN_PERMISSIONS if rbac.allowed(p.roles, perm))


def _insert(cur, p: Principal, key: UUID, version: int, body: MemoryIn) -> dict:
    cur.execute(
        "INSERT INTO aav.memory_items (tenant_id, key, version, kind, title, content, source_kind, source_ref, "
        "required_permission, contains_personal_data, consent_basis, retain_until, created_by) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id, key, version, created_at, retain_until",
        (p.tenant_id, key, version, body.kind, body.title, body.content, body.source_kind, body.source_ref,
         body.required_permission, body.contains_personal_data, body.consent_basis,
         _retain_until(cur, body.retain_days), p.actor))
    return cur.fetchone()


@router.post("", status_code=201)
def remember(body: MemoryIn, p: Principal = Depends(need("memory.write"))):
    if not rbac.allowed(p.roles, body.required_permission):
        raise HTTPException(403, "cannot restrict an item to a permission you do not hold")
    with db.tenant_tx(p.tenant_id) as cur:
        row = _insert(cur, p, uuid.uuid4(), 1, body)
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="memory.create", target=str(row["key"]),
                     detail={"kind": body.kind, "source": f"{body.source_kind}:{body.source_ref}",
                             "personal_data": body.contains_personal_data})
    return row


def _current(cur, key: UUID, p: Principal) -> dict:
    cur.execute("SELECT * FROM aav.memory_items WHERE key = %s AND superseded_at IS NULL "
                "AND required_permission = ANY(%s)", (key, _allowed_perms(p)))
    row = cur.fetchone()
    if not row:
        raise HTTPException(404, "not found")
    return row


@router.put("/{key}")
def revise(key: UUID, body: MemoryIn, p: Principal = Depends(need("memory.write"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur_row = _current(cur, key, p)
        cur.execute("UPDATE aav.memory_items SET superseded_at = now() WHERE id = %s", (cur_row["id"],))
        row = _insert(cur, p, key, cur_row["version"] + 1, body)
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="memory.revise", target=str(key),
                     detail={"version": row["version"]})
    return row


def _public(r: dict) -> dict:
    r = {k: v for k, v in r.items() if k not in ("tsv", "tenant_id")}
    return r


@router.get("/search")
def search(q: str, limit: int = 10, p: Principal = Depends(need("memory.read"))):
    return retrieve(RetrieveIn(query=q, k=max(1, min(limit, 50))), p)


@router.post("/retrieve")
def retrieve(body: RetrieveIn, p: Principal = Depends(need("memory.read"))):
    """RAG retrieval: ranked passages the caller may see, each with its source attribution."""
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute(
            "SELECT key, version, kind, title, content, source_kind, source_ref, created_by, created_at, "
            "ts_rank(tsv, websearch_to_tsquery('simple', %s)) AS score FROM aav.memory_items "
            "WHERE superseded_at IS NULL AND required_permission = ANY(%s) "
            "AND tsv @@ websearch_to_tsquery('simple', %s) AND (%s::text[] IS NULL OR kind = ANY(%s)) "
            "ORDER BY score DESC, created_at DESC LIMIT %s",
            (body.query, _allowed_perms(p), body.query, body.kinds, body.kinds, body.k))
        rows = cur.fetchall()
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="memory.retrieve", target="",
                     detail={"query_chars": len(body.query), "results": len(rows)})
    return {"query": body.query, "passages": [
        {"text": r["content"][:2000], "title": r["title"], "score": round(float(r["score"]), 4),
         "citation": {"memory_key": str(r["key"]), "version": r["version"], "kind": r["kind"],
                      "source": f"{r['source_kind']}:{r['source_ref']}" if r["source_ref"] else r["source_kind"],
                      "created_by": r["created_by"], "created_at": r["created_at"].isoformat()}} for r in rows]}


@router.get("/{key}")
def get_item(key: UUID, p: Principal = Depends(need("memory.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        return _public(_current(cur, key, p))


@router.get("/{key}/versions")
def versions(key: UUID, p: Principal = Depends(need("memory.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT * FROM aav.memory_items WHERE key = %s AND required_permission = ANY(%s) "
                    "ORDER BY version DESC", (key, _allowed_perms(p)))
        rows = cur.fetchall()
    if not rows:
        raise HTTPException(404, "not found")
    return [_public(r) for r in rows]


@router.delete("/{key}")
def forget(key: UUID, p: Principal = Depends(need("memory.write"))):
    with db.tenant_tx(p.tenant_id) as cur:
        _current(cur, key, p)
        cur.execute("DELETE FROM aav.memory_items WHERE key = %s", (key,))
        n = cur.rowcount
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="memory.erase", target=str(key),
                     detail={"versions_deleted": n})
    return {"erased_versions": n}
