"""Durable, tenant-scoped job queue and exact-argument HITL tool approvals."""
import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import ForeignKeyConstraint, String, select, text
from sqlalchemy.orm import Mapped, mapped_column, Session
from pydantic import BaseModel, Field
from .main import Base, Principal
from .supervisor import AgentRun, audit

class AgentJob(Base):
    __tablename__ = "ide_agent_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128))
    run_id: Mapped[str] = mapped_column(String(36))
    state: Mapped[str] = mapped_column(String(24), default="pending")
    attempt: Mapped[int] = mapped_column(default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(100))
    lease_until: Mapped[datetime | None] = mapped_column()
    __table_args__ = (ForeignKeyConstraint(["tenant_id","run_id"], ["ide_agent_runs.tenant_id","ide_agent_runs.id"]),)

class ToolApproval(Base):
    __tablename__ = "ide_tool_approvals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128))
    run_id: Mapped[str] = mapped_column(String(36))
    server_name: Mapped[str] = mapped_column(String(100))
    tool_name: Mapped[str] = mapped_column(String(120))
    args_sha256: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16), default="pending")
    requested_by: Mapped[str] = mapped_column(String(255))
    decided_by: Mapped[str | None] = mapped_column(String(255))
    __table_args__ = (ForeignKeyConstraint(["tenant_id","run_id"], ["ide_agent_runs.tenant_id","ide_agent_runs.id"]),)

class ToolRequest(BaseModel):
    server: str = Field(min_length=1, max_length=100)
    tool: str = Field(min_length=1, max_length=120)
    arguments: dict = Field(default_factory=dict)

def digest_arguments(arguments: dict) -> str:
    encoded = json.dumps(arguments, sort_keys=True, separators=(",",":"), allow_nan=False)
    if len(encoded) > 4000:
        raise ValueError("Tool arguments exceed limit")
    return hashlib.sha256(encoded.encode()).hexdigest()

def enqueue(db: Session, p: Principal, run_id: str) -> AgentJob:
    if p.role not in ("owner","admin"):
        raise PermissionError("Owner/admin required")
    run = db.scalar(select(AgentRun).where(AgentRun.tenant_id==p.tenant_id,AgentRun.id==run_id).with_for_update())
    if run is None:
        raise LookupError("Run not found")
    if run.status != "approved":
        raise ValueError("Run not approved")
    existing = db.scalar(select(AgentJob).where(AgentJob.tenant_id==p.tenant_id,AgentJob.run_id==run_id))
    if existing:
        return existing
    job = AgentJob(id=str(uuid.uuid4()),tenant_id=p.tenant_id,run_id=run_id,state="pending",attempt=0)
    db.add(job)
    audit(db,p,run_id,"queued")
    db.commit()
    return job

def claim(db: Session, tenant_id: str, owner: str, lease_seconds: int=60) -> tuple[str,str] | None:
    if not 5 <= lease_seconds <= 300 or not owner or len(owner)>100:
        raise ValueError("Invalid lease")
    # Lease reclamation is safe for the queue state, but external model calls are NOT
    # exactly-once. Use fencing tokens and provider idempotency before live activation.
    job = db.scalar(select(AgentJob).where(
        AgentJob.tenant_id==tenant_id,
        ((AgentJob.state=="pending") | ((AgentJob.state=="leased") & (AgentJob.lease_until < datetime.now(timezone.utc))))
    ).order_by(AgentJob.id).with_for_update(skip_locked=True).limit(1))
    if job is None:
        return None
    run = db.scalar(select(AgentRun).where(AgentRun.id==job.run_id,AgentRun.tenant_id==tenant_id).with_for_update())
    if run is None or run.status not in ("approved","running") or job.attempt>=2:
        job.state="cancelled" if run is None or run.status=="cancelled" else "failed"
        db.commit()
        return None
    job.state="leased"
    job.lease_owner=owner
    job.lease_until=datetime.now(timezone.utc)+timedelta(seconds=lease_seconds)
    job.attempt+=1
    db.commit()
    return (job.id,job.run_id)

def request_tool(db: Session, p: Principal, run_id: str, body: ToolRequest) -> ToolApproval:
    from .agent_runtime import approved_mcp_tool
    approved_mcp_tool(body.server,body.tool)
    run = db.scalar(select(AgentRun).where(AgentRun.tenant_id==p.tenant_id,AgentRun.id==run_id))
    if run is None:
        raise LookupError("Run not found")
    if p.role not in ("owner","admin","editor"):
        raise PermissionError("Editor required")
    digest=digest_arguments(body.arguments)
    existing=db.scalar(select(ToolApproval).where(ToolApproval.tenant_id==p.tenant_id,
      ToolApproval.run_id==run_id,ToolApproval.server_name==body.server,
      ToolApproval.tool_name==body.tool,ToolApproval.args_sha256==digest))
    if existing:
        return existing
    approval=ToolApproval(id=str(uuid.uuid4()),tenant_id=p.tenant_id,run_id=run_id,
      server_name=body.server,tool_name=body.tool,args_sha256=digest,requested_by=p.subject,state="pending")
    db.add(approval)
    audit(db,p,run_id,"tool_requested")
    db.commit()
    return approval

def decide_tool(db: Session, p: Principal, approval_id: str, approved: bool) -> ToolApproval:
    if p.role not in ("owner","admin"):
        raise PermissionError("Owner/admin required")
    item=db.scalar(select(ToolApproval).where(ToolApproval.tenant_id==p.tenant_id,
      ToolApproval.id==approval_id).with_for_update())
    if item is None:
        raise LookupError("Approval not found")
    if item.state!="pending":
        raise ValueError("Already decided")
    item.state="approved" if approved else "rejected"
    item.decided_by=p.subject
    audit(db,p,item.run_id,"tool_approved" if approved else "tool_rejected")
    db.commit()
    return item

def consume_tool(db: Session, tenant_id: str, run_id: str, server: str, tool: str, arguments: dict) -> None:
    digest=digest_arguments(arguments)
    item=db.scalar(select(ToolApproval).where(ToolApproval.tenant_id==tenant_id,
      ToolApproval.run_id==run_id,ToolApproval.server_name==server,
      ToolApproval.tool_name==tool,ToolApproval.args_sha256==digest).with_for_update())
    if item is None or item.state!="approved":
        raise PermissionError("Exact tool call not approved")
    item.state="consumed"
    db.commit()
