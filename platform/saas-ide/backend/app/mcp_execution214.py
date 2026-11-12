"""Phase 2.14 fail-closed MCP dispatch lifecycle.

An external outcome may be unknown after dispatch. Never replay it automatically.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session
from .phase23 import _scope


def begin_dispatch(db: Session, tenant: str, run_id: str, approval_id: str) -> str:
    """Atomically claim a reserved execution and return its stable key.

    Only a reserved execution may transition to dispatching. A retry after
    dispatch began fails closed, even if the previous worker crashed.
    """
    _scope(db, tenant)
    # Serialize final dispatch authorization with cancellation.
    active = db.execute(text("""SELECT id FROM ide_agent_runs
        WHERE tenant_id=:tenant AND id=:run
          AND status IN ('approved','running') FOR UPDATE"""),
        {"tenant":tenant,"run":run_id}).first()
    if active is None:
        db.rollback()
        raise PermissionError("MCP run inactive or cancelled before dispatch")
    row = db.execute(text("""UPDATE ide_mcp_executions e SET
        state='dispatching',dispatch_started_at=now()
        WHERE e.tenant_id=:tenant AND e.run_id=:run AND e.approval_id=:approval
          AND e.state='reserved'
          AND EXISTS (SELECT 1 FROM ide_agent_runs r
             WHERE r.tenant_id=e.tenant_id AND r.id=e.run_id
               AND r.status IN ('approved','running'))
        RETURNING e.idempotency_key"""),
        {"tenant":tenant,"run":run_id,"approval":approval_id}).first()
    if row is None:
        db.rollback()
        raise PermissionError("MCP execution not reserved, run inactive or already dispatched")
    db.commit()
    return row[0]


def complete_dispatch(db: Session, tenant: str, run_id: str,
                      approval_id: str, success: bool) -> bool:
    _scope(db, tenant)
    row = db.execute(text("""UPDATE ide_mcp_executions
        SET state=:state,completed_at=now()
        WHERE tenant_id=:tenant AND run_id=:run AND approval_id=:approval
          AND state='dispatching' RETURNING id"""),
        {"state":"succeeded" if success else "failed",
         "tenant":tenant,"run":run_id,"approval":approval_id}).first()
    db.commit()
    return row is not None


def mark_unknown(db: Session, tenant: str, run_id: str,
                 approval_id: str) -> bool:
    """Persist uncertain outcome; never retry or reset to reserved."""
    _scope(db, tenant)
    row = db.execute(text("""UPDATE ide_mcp_executions
        SET state='outcome_unknown',completed_at=now()
        WHERE tenant_id=:tenant AND run_id=:run AND approval_id=:approval
          AND state='dispatching' RETURNING id"""),
        {"tenant":tenant,"run":run_id,"approval":approval_id}).first()
    db.commit()
    return row is not None


def reconcile_stale(db: Session, tenant: str, older_than_seconds: int = 300) -> int:
    """Quarantine stale dispatches for manual/provider reconciliation."""
    if not 30 <= older_than_seconds <= 86400:
        raise ValueError("Invalid recovery age")
    _scope(db, tenant)
    rows = db.execute(text("""UPDATE ide_mcp_executions
        SET state='outcome_unknown',completed_at=now()
        WHERE tenant_id=:tenant AND state='dispatching'
          AND dispatch_started_at < now()-(:age * interval '1 second')
        RETURNING id"""), {"tenant":tenant,"age":older_than_seconds}).all()
    db.commit()
    return len(rows)


def execution_status(db: Session, tenant: str, approval_id: str) -> dict | None:
    """Read-only, tenant-scoped operational status without credentials or arguments."""
    _scope(db, tenant)
    row = db.execute(text("""SELECT id,run_id,idempotency_key,state,
        created_at,dispatch_started_at,completed_at
        FROM ide_mcp_executions WHERE tenant_id=:tenant AND approval_id=:approval"""),
        {"tenant":tenant,"approval":approval_id}).mappings().first()
    db.rollback()
    return dict(row) if row else None


def resolve_unknown(db: Session, tenant: str, run_id: str, approval_id: str,
                    *, verified_outcome: str, actor: str, evidence_reference: str,
                    principal=None, evidence_verifier=None) -> bool:
    """Manual reconciliation requires an externally verified outcome.

    This never resets a dispatch to reserved and never triggers a replay.
    """
    # This is a privileged service function, not a public unauthenticated API.
    if principal is None or principal.tenant_id != tenant or principal.role not in ("owner", "admin"):
        raise PermissionError("Tenant owner/admin authorization required")
    if principal.subject != actor:
        raise PermissionError("Reconciliation actor must match authenticated principal")
    if evidence_verifier is None or not callable(evidence_verifier):
        raise PermissionError("Independent evidence verifier required")
    if verified_outcome not in ("succeeded", "failed"):
        raise ValueError("Verified outcome must be succeeded or failed")
    if not actor or len(actor)>255 or not evidence_reference or len(evidence_reference)>160:
        raise ValueError("Authorized actor and evidence reference required")
    # Fail closed unless a trusted provider adapter validates the evidence.
    if evidence_verifier(tenant, run_id, approval_id, verified_outcome, evidence_reference) is not True:
        raise PermissionError("Provider evidence could not be verified")
    _scope(db, tenant)
    from .supervisor import AgentAudit
    import uuid
    try:
        row = db.execute(text("""UPDATE ide_mcp_executions
            SET state=:outcome,completed_at=now(), reconciliation_reference=:evidence, reconciled_by=:actor
            WHERE tenant_id=:tenant AND run_id=:run AND approval_id=:approval
              AND state='outcome_unknown' RETURNING id"""),
            {"outcome":verified_outcome,"tenant":tenant,"run":run_id,
             "approval":approval_id,"evidence":evidence_reference,"actor":actor}).first()
        if row is None:
            db.rollback()
            return False
        db.add(AgentAudit(id=str(uuid.uuid4()), tenant_id=tenant, run_id=run_id,
                          actor=actor, action="mcp_reconciled"))
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
