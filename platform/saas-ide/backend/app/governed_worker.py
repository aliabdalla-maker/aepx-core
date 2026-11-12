"""Explicit one-job governed executor; no daemon or automatic dispatch.

A successful claim is an at-least-once reservation, not exactly-once provider execution.
Never enable without a reviewed network sandbox and provider spend reconciliation.
"""
import os
import uuid
from sqlalchemy import text
from .main import SessionLocal
from .phase23 import fenced_claim, reserve_budget, settle_reserved_maximum, record_fenced_result
from .timeout23 import hard_deadline
from .providers import generate

def execute_next(tenant_id: str, *, owner: str | None = None,
                 inference=generate) -> str:
    # Check all gates before claiming a job. No credentials or outbound calls by default.
    if os.getenv("IDE_EXTERNAL_EXECUTION_ENABLED")!="true" or os.getenv("IDE_GOVERNED_WORKER_ENABLED")!="true":
        raise PermissionError("Governed worker disabled")
    if os.getenv("IDE_EGRESS_GATEWAY_VERIFIED")!="true":
        raise PermissionError("Reviewed network egress gateway required")
    if inference is generate and os.getenv("IDE_PROVIDER_USAGE_RECONCILIATION_ENABLED")!="true":
        raise PermissionError("Provider spend reconciliation required")
    if not tenant_id or len(tenant_id)>128:
        raise ValueError("Invalid tenant")
    # No implicit price fallback. Ceiling covers a bounded input+output envelope.
    tokens=int(os.getenv("IDE_WORKER_MAX_TOKENS","0"))
    cost=int(os.getenv("IDE_WORKER_MAX_MICROUSD","0"))
    seconds=int(os.getenv("IDE_WORKER_TIMEOUT_SECONDS","0"))
    if not 1<=tokens<=2000 or not 1<=cost<=5_000_000 or not 1<=seconds<=30:
        raise ValueError("Worker budgets and deadline must be explicitly configured")
    owner=owner or str(uuid.uuid4())
    with SessionLocal() as db:
        claim=fenced_claim(db,tenant_id,owner,lease_seconds=60)
    if claim is None:
        return "empty"
    job_id,run_id,fence=claim["job_id"],claim["run_id"],claim["fencing_token"]
    reservation=None
    try:
        with SessionLocal() as db:
            reservation=reserve_budget(db,tenant_id,job_id,fence,tokens,cost)
        with SessionLocal() as db:
            db.execute(text("SELECT set_config('ide.tenant_id',:tenant,true)"),{"tenant":tenant_id})
            row=db.execute(text("""SELECT r.model_route,r.request FROM ide_agent_runs r
              JOIN ide_agent_jobs j ON j.run_id=r.id AND j.tenant_id=r.tenant_id
              WHERE r.tenant_id=:tenant AND j.id=:job AND j.fencing_token=:fence
                AND j.lease_owner=:owner AND j.state='leased'
                AND j.lease_until>now() AND r.status IN ('approved','running')"""),
                {"tenant":tenant_id,"job":job_id,"fence":fence,"owner":owner}).first()
            db.rollback()
        if row is None or row.model_route=="unconfigured":
            raise PermissionError("Job no longer authorised or provider unconfigured")
        output=hard_deadline(inference,row.model_route,row.request,max_tokens=tokens,seconds=seconds)
        if not isinstance(output,str):
            raise ValueError("Provider output must be text")
        success=True
    except Exception:
        output="Execution failed or timed out; inspect restricted audit logs"
        success=False
    finally:
        # Unknown provider usage is charged at the maximum reserved envelope.
        # This prevents overspend by repeated unmetered retries, but requires
        # external reconciliation for provider charges after crashes.
        if reservation is not None:
            with SessionLocal() as db:
                settle_reserved_maximum(db,tenant_id,reservation)
    with SessionLocal() as db:
        committed=record_fenced_result(db,tenant_id,job_id,owner,fence,output,success)
    return ("completed" if success else "failed") if committed else "stale_or_cancelled"
