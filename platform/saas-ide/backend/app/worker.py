"""Fail-closed, synchronous worker core. Invoke from a separately authorised worker process only."""
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .main import SessionLocal
from .supervisor import AgentRun
from .providers import generate

MAX_ATTEMPTS = 2

def execute_one(tenant_id: str, run_id: str, *, inference=generate) -> str:
    if os.getenv("IDE_EXTERNAL_EXECUTION_ENABLED") != "true":
        raise PermissionError("Worker execution disabled by default")
    if not tenant_id or len(tenant_id) > 128:
        raise ValueError("Invalid tenant")
    # Dedicated worker DB role must have RLS enabled and no BYPASSRLS.
    with SessionLocal() as db:
        db.execute(text("SELECT set_config('ide.tenant_id', :tenant, true)"), {"tenant": tenant_id})
        # Atomic claim prevents concurrent workers from executing the same approved run.
        run = db.scalar(select(AgentRun).where(
            AgentRun.id == run_id, AgentRun.tenant_id == tenant_id
        ).with_for_update(skip_locked=True))
        if run is None or run.status != "approved":
            db.rollback()
            return "not_claimed"
        if run.attempts >= MAX_ATTEMPTS:
            run.status = "failed"
            db.commit()
            return "attempt_limit"
        if run.model_route == "unconfigured":
            run.status = "failed"
            run.result = "No model configured"
            db.commit()
            return "unconfigured"
        run.attempts += 1
        run.status = "running"
        prompt, provider = run.request, run.model_route
        db.commit()
    try:
        output = inference(provider, prompt, max_tokens=1200)
        outcome = "completed"
    except Exception:
        output, outcome = "Execution failed; inspect restricted worker logs", "failed"
    with SessionLocal() as db:
        db.execute(text("SELECT set_config('ide.tenant_id', :tenant, true)"), {"tenant": tenant_id})
        run = db.scalar(select(AgentRun).where(
            AgentRun.id == run_id, AgentRun.tenant_id == tenant_id
        ).with_for_update())
        if run is None:
            db.rollback()
            return "missing"
        if run.status == "cancelled":
            db.rollback()
            return "cancelled"
        if run.status != "running":
            db.rollback()
            return "state_changed"
        run.result = output[:20000]
        run.status = outcome
        db.commit()
    return outcome
