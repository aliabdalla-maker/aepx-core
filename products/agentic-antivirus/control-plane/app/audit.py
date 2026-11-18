"""Append-only, hash-chained audit trail (FN-02, AX-10, OBJ-07, VFS-17, SET-06)."""
from __future__ import annotations

import json


def record(cur, *, tenant_id, actor: str, action: str, target: str = "", detail: dict | None = None,
           trace_id: str | None = None) -> int:
    cur.execute(
        "INSERT INTO aav.audit_log (tenant_id, actor, action, target, detail, trace_id) "
        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (str(tenant_id) if tenant_id else None, actor, action, target, json.dumps(detail or {}, default=str), trace_id),
    )
    return cur.fetchone()["id"]


def verify_chain(cur) -> dict:
    """Recompute the visible chain (current tenant) and report the first break, if any."""
    cur.execute(
        "SELECT id, prev_hash, hash, encode(digest(prev_hash || '|' || COALESCE(tenant_id::text,'') || '|' || actor "
        "|| '|' || action || '|' || target || '|' || detail::text || '|' || "
        "to_char(at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US'), 'sha256'), 'hex') AS recomputed "
        "FROM aav.audit_log ORDER BY id")
    rows = cur.fetchall()
    prev = "0" * 64
    for r in rows:
        if r["prev_hash"] != prev or r["hash"] != r["recomputed"]:
            return {"valid": False, "entries": len(rows), "first_break_id": r["id"]}
        prev = r["hash"]
    return {"valid": True, "entries": len(rows), "head": prev}
