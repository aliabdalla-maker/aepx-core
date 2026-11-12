"""Phase 2 governed supervisor. Planning is deterministic; external actions are approval gated."""
import os
import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import ForeignKeyConstraint, String, Text, select, text
from sqlalchemy.orm import Mapped, Session, mapped_column

from .main import Base, Principal, Project, project_or_404


class AgentRun(Base):
    __tablename__ = "ide_agent_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    request: Mapped[str] = mapped_column(Text, nullable=False)
    model_route: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="awaiting_approval")
    plan: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[str] = mapped_column(Text, nullable=False, default="")
    attempts: Mapped[int] = mapped_column(nullable=False, default=0)
    __table_args__ = (ForeignKeyConstraint(["tenant_id", "project_id"], ["ide_projects.tenant_id", "ide_projects.id"]),)


class AgentAudit(Base):
    __tablename__ = "ide_agent_audit"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    __table_args__ = (ForeignKeyConstraint(["tenant_id", "run_id"], ["ide_agent_runs.tenant_id", "ide_agent_runs.id"]),)


def audit(db: Session, p: Principal, run_id: str, action: str) -> None:
    db.add(AgentAudit(id=str(uuid.uuid4()), tenant_id=p.tenant_id, run_id=run_id,
                      actor=p.subject, action=action))


class KnowledgeDocument(Base):
    __tablename__ = "ide_knowledge_documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (ForeignKeyConstraint(["tenant_id", "project_id"], ["ide_projects.tenant_id", "ide_projects.id"]),)


class RunRequest(BaseModel):
    project_id: str
    task: str = Field(min_length=5, max_length=4000)
    preferred_provider: Literal["oci", "openai", "anthropic", "gemini"] | None = None


class KnowledgeIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=20000)


class SearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=200)


PROVIDERS = ("oci", "openai", "anthropic", "gemini")


def route_model(preferred: str | None = None) -> str:
    enabled = [p for p in PROVIDERS if os.getenv("IDE_LLM_" + p.upper() + "_ENABLED") == "true"]
    if preferred:
        if preferred not in enabled:
            raise ValueError("Requested provider is not enabled")
        return preferred
    if not enabled:
        return "unconfigured"
    priority = os.getenv("IDE_LLM_PRIORITY", "oci,openai,anthropic,gemini").split(",")
    return next((p for p in priority if p in enabled), enabled[0])


def plan_steps(task: str) -> list[dict]:
    return [
        {"agent": "requirements", "action": "analyse", "goal": task},
        {"agent": "architect", "action": "design", "goal": "Produce architecture and security boundaries"},
        {"agent": "developer", "action": "propose", "goal": "Prepare proposed changes without executing code"},
        {"agent": "verifier", "action": "review", "goal": "Review risks, tests and approval requirements"},
    ]


def create_run(db: Session, p: Principal, body: RunRequest) -> AgentRun:
    if p.role not in ("owner", "admin", "editor"):
        raise PermissionError("Read-only membership")
    project_or_404(db, p.tenant_id, body.project_id)
    route = route_model(body.preferred_provider)
    import json
    run = AgentRun(id=str(uuid.uuid4()), tenant_id=p.tenant_id, project_id=body.project_id,
                   subject=p.subject, request=body.task, model_route=route,
                   status="awaiting_approval", plan=json.dumps(plan_steps(body.task)))
    db.add(run)
    db.flush()
    audit(db, p, run.id, "created")
    db.commit()
    return run


def get_run(db: Session, p: Principal, run_id: str) -> AgentRun | None:
    return db.scalar(select(AgentRun).where(AgentRun.id == run_id, AgentRun.tenant_id == p.tenant_id))


def decide(db: Session, p: Principal, run_id: str, approve: bool) -> AgentRun:
    run = get_run(db, p, run_id)
    if run is None:
        raise LookupError("Run not found")
    if p.role not in ("owner", "admin"):
        raise PermissionError("Only owners/admins can approve")
    if run.status != "awaiting_approval":
        raise ValueError("Run already decided")
    # Approval authorizes a planning-only worker, not arbitrary tool/code execution.
    run.status = "approved" if approve else "rejected"
    audit(db, p, run.id, "approved" if approve else "rejected")
    db.commit()
    return run


def cancel(db: Session, p: Principal, run_id: str) -> AgentRun:
    run = get_run(db, p, run_id)
    if run is None:
        raise LookupError("Run not found")
    if p.role not in ("owner", "admin") and p.subject != run.subject:
        raise PermissionError("Only requestor or owner/admin may cancel")
    if run.status not in ("awaiting_approval", "approved", "running", "failed"):
        raise ValueError("Run cannot be cancelled")
    run.status = "cancelled"
    audit(db, p, run.id, "cancelled")
    db.commit()
    return run


def retry(db: Session, p: Principal, run_id: str) -> AgentRun:
    run = get_run(db, p, run_id)
    if run is None:
        raise LookupError("Run not found")
    if p.role not in ("owner", "admin"):
        raise PermissionError("Only owner/admin may retry")
    if run.status != "failed" or run.attempts >= 2:
        raise ValueError("Retry not permitted")
    run.status = "awaiting_approval"
    run.result = ""
    audit(db, p, run.id, "retry_requested")
    db.commit()
    return run


def search_knowledge(db: Session, p: Principal, project_id: str, query: str) -> list[dict]:
    project_or_404(db, p.tenant_id, project_id)
    # Phase 2 lexical retrieval; no embedding or vector index is claimed.
    docs = db.scalars(select(KnowledgeDocument).where(
        KnowledgeDocument.tenant_id == p.tenant_id,
        KnowledgeDocument.project_id == project_id
    ).limit(200)).all()
    words = [w.lower() for w in query.split() if len(w) > 1]
    scored = sorted(
        ((sum(doc.content.lower().count(w) + doc.title.lower().count(w) for w in words), doc) for doc in docs),
        key=lambda x: x[0], reverse=True
    )
    return [{"id": d.id, "title": d.title, "excerpt": d.content[:600], "score": score}
            for score, d in scored[:5] if score > 0]


def save_knowledge(db: Session, p: Principal, project_id: str, body: KnowledgeIn) -> KnowledgeDocument:
    if p.role not in ("owner", "admin", "editor"):
        raise PermissionError("Read-only membership")
    project_or_404(db, p.tenant_id, project_id)
    doc = KnowledgeDocument(id=str(uuid.uuid4()), tenant_id=p.tenant_id, project_id=project_id,
                            title=body.title, content=body.content)
    db.add(doc)
    db.commit()
    return doc
