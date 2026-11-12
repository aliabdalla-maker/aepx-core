"""Hybrid IDE Phase 1 API. OIDC access tokens + explicit PostgreSQL tenant membership."""
import os
import uuid
from functools import lru_cache
from typing import Annotated

import jwt
from jwt import PyJWKClient
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import String, Text, create_engine, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

DATABASE_URL = os.getenv("IDE_DATABASE_URL", "")
if not DATABASE_URL.startswith(("postgresql+psycopg://", "postgresql://")):
    raise RuntimeError("IDE_DATABASE_URL must specify PostgreSQL (psycopg)")
OIDC_ISSUER = os.getenv("IDE_OIDC_ISSUER", "").rstrip("/")
OIDC_AUDIENCE = os.getenv("IDE_OIDC_AUDIENCE", "")
OIDC_JWKS_URL = os.getenv("IDE_OIDC_JWKS_URL", "")
if not OIDC_ISSUER.startswith("https://") or not OIDC_AUDIENCE or not OIDC_JWKS_URL.startswith("https://"):
    raise RuntimeError("HTTPS IDE_OIDC_ISSUER, IDE_OIDC_JWKS_URL and IDE_OIDC_AUDIENCE are required")
if "/.well-known/" in OIDC_ISSUER:
    raise RuntimeError("Use issuer URL, not discovery URL")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
app = FastAPI(title="AEP-X Hybrid IDE API", version="0.2.0")
origin = os.getenv("IDE_WEB_ORIGIN", "http://localhost:3000")
app.add_middleware(CORSMiddleware, allow_origins=[origin], allow_methods=["GET", "POST", "PUT"], allow_headers=["Authorization", "Content-Type", "X-Tenant-ID"])


class Base(DeclarativeBase):
    pass


class Membership(Base):
    __tablename__ = "ide_memberships"
    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    subject: Mapped[str] = mapped_column(String(255), primary_key=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)


class Project(Base):
    __tablename__ = "ide_projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")


class WorkspaceFile(Base):
    __tablename__ = "ide_workspace_files"
    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    path: Mapped[str] = mapped_column(String(255), primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")


def db_session(tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None):
    if not tenant_id or len(tenant_id) > 128:
        raise HTTPException(400, "X-Tenant-ID required")
    with SessionLocal() as db:
        # Header only selects a row-level scope; it does NOT authenticate membership.
        # SET LOCAL expires at transaction end and prevents pool tenant leakage.
        db.execute(text("SELECT set_config('ide.tenant_id', :tenant, true)"), {"tenant": tenant_id})
        try:
            yield db
        finally:
            db.rollback()


@lru_cache(maxsize=1)
def jwks_client():
    return PyJWKClient(OIDC_JWKS_URL, cache_jwk_set=True, lifespan=300)


def verified_subject(authorization: Annotated[str | None, Header()] = None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Bearer token required")
    token = authorization[7:]
    try:
        key = jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(token, key.key, algorithms=["RS256"], audience=OIDC_AUDIENCE, issuer=OIDC_ISSUER, options={"require": ["exp", "iat", "iss", "aud", "sub"]}, leeway=30)
        subject = claims["sub"]
        if not isinstance(subject, str) or not subject or len(subject) > 255:
            raise ValueError("Invalid subject")
        return subject
    except Exception:
        # Never echo token or internal signing details.
        raise HTTPException(401, "Invalid access token") from None


class Principal(BaseModel):
    subject: str
    tenant_id: str
    role: str


def principal(
    subject: str = Depends(verified_subject),
    tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
    db: Session = Depends(db_session),
) -> Principal:
    if not tenant_id or len(tenant_id) > 128:
        raise HTTPException(400, "X-Tenant-ID required")
    member = db.get(Membership, (tenant_id, subject))
    if member is None:
        raise HTTPException(403, "Not a member of this tenant")
    return Principal(subject=subject, tenant_id=tenant_id, role=member.role)


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)


class ProjectOut(ProjectIn):
    id: str


class FileIn(BaseModel):
    content: str = Field(max_length=1_000_000)


def project_or_404(db: Session, tenant: str, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.tenant_id != tenant:
        raise HTTPException(404, "Project not found")
    return project


def safe_path(path: str) -> str:
    if not path or len(path) > 255 or path.startswith("/") or "\\" in path or any(p in ("", ".", "..") for p in path.split("/")):
        raise HTTPException(400, "Invalid workspace path")
    return path


@app.get("/health")
def health():
    return {"status": "ok", "service": "hybrid-ide-api"}


@app.get("/api/v1/me")
def me(p: Principal = Depends(principal)):
    return p


@app.post("/api/v1/projects", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectIn, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    if p.role not in ("owner", "admin", "editor"):
        raise HTTPException(403, "Read-only membership")
    project = Project(id=str(uuid.uuid4()), tenant_id=p.tenant_id, name=body.name, description=body.description)
    db.add(project)
    db.commit()
    return ProjectOut(id=project.id, name=project.name, description=project.description)


@app.get("/api/v1/projects", response_model=list[ProjectOut])
def list_projects(p: Principal = Depends(principal), db: Session = Depends(db_session)):
    projects = db.scalars(select(Project).where(Project.tenant_id == p.tenant_id).order_by(Project.name)).all()
    return [ProjectOut(id=x.id, name=x.name, description=x.description) for x in projects]


@app.get("/api/v1/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    x = project_or_404(db, p.tenant_id, project_id)
    return ProjectOut(id=x.id, name=x.name, description=x.description)


@app.get("/api/v1/projects/{project_id}/files")
def list_files(project_id: str, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    project_or_404(db, p.tenant_id, project_id)
    files = db.scalars(select(WorkspaceFile).where(WorkspaceFile.tenant_id == p.tenant_id, WorkspaceFile.project_id == project_id)).all()
    return [{"path": x.path, "content": x.content} for x in files]


@app.put("/api/v1/projects/{project_id}/files/{path:path}")
def save_file(project_id: str, path: str, body: FileIn, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    if p.role not in ("owner", "admin", "editor"):
        raise HTTPException(403, "Read-only membership")
    project_or_404(db, p.tenant_id, project_id)
    path = safe_path(path)
    file = db.get(WorkspaceFile, (p.tenant_id, project_id, path))
    if file is None:
        file = WorkspaceFile(tenant_id=p.tenant_id, project_id=project_id, path=path, content=body.content)
        db.add(file)
    else:
        file.content = body.content
    db.commit()
    return {"path": path, "saved": True}

# Phase 2 endpoints reuse the verified OIDC subject and tenant-scoped DB session.
from .supervisor import RunRequest, KnowledgeIn, SearchIn, AgentRun, KnowledgeDocument, create_run, get_run, decide, search_knowledge, save_knowledge, route_model
from .agent_runtime import allowed_mcp_endpoint

@app.post("/api/v1/agent-runs", status_code=201)
def submit_agent_run(body: RunRequest, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    try:
        run = create_run(db, p, body)
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"id": run.id, "status": run.status, "model_route": run.model_route, "plan": run.plan}

@app.get("/api/v1/agent-runs/{run_id}")
def agent_run_detail(run_id: str, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    run = get_run(db, p, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    return {"id": run.id, "status": run.status, "model_route": run.model_route, "plan": run.plan, "result": run.result}

@app.post("/api/v1/agent-runs/{run_id}/decision")
def decide_agent_run(run_id: str, approved: bool, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    try:
        run = decide(db, p, run_id, approved)
    except LookupError:
        raise HTTPException(404, "Run not found")
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return {"id": run.id, "status": run.status, "execution_started": False}

@app.post("/api/v1/projects/{project_id}/knowledge", status_code=201)
def add_knowledge(project_id: str, body: KnowledgeIn, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    try:
        doc = save_knowledge(db, p, project_id, body)
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    return {"id": doc.id, "title": doc.title}

@app.post("/api/v1/projects/{project_id}/knowledge/search")
def query_knowledge(project_id: str, body: SearchIn, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    return {"matches": search_knowledge(db, p, project_id, body.query)}

@app.get("/api/v1/agent-capabilities")
def agent_capabilities(p: Principal = Depends(principal)):
    return {"providers": {name: os.getenv("IDE_LLM_" + name.upper() + "_ENABLED") == "true"
                            for name in ("oci", "openai", "anthropic", "gemini")},
            "crewai_execution_enabled": False,
            "mcp_allowlisted_servers": ["knowledge", "github-readonly"],
            "mcp_execution_enabled": False,
            "knowledge_retrieval": "lexical",
            "approval_required": True}

from .supervisor import cancel as cancel_agent_run, retry as retry_agent_run, AgentAudit
from .rag import index_document, search_vectors

@app.get("/api/v1/projects/{project_id}/agent-runs")
def list_agent_runs(project_id: str, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    project_or_404(db, p.tenant_id, project_id)
    runs = db.scalars(select(AgentRun).where(
        AgentRun.tenant_id == p.tenant_id, AgentRun.project_id == project_id
    ).order_by(AgentRun.id.desc()).limit(50)).all()
    return [{"id": r.id, "status": r.status, "model_route": r.model_route,
             "task": r.request[:200], "attempts": r.attempts, "result": r.result[:500]}
            for r in runs]

@app.get("/api/v1/agent-runs/{run_id}/audit")
def agent_audit(run_id: str, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    if get_run(db, p, run_id) is None:
        raise HTTPException(404, "Run not found")
    records = db.scalars(select(AgentAudit).where(
        AgentAudit.tenant_id == p.tenant_id, AgentAudit.run_id == run_id
    ).order_by(AgentAudit.id).limit(100)).all()
    return [{"actor": a.actor, "action": a.action} for a in records]

@app.post("/api/v1/agent-runs/{run_id}/cancel")
def cancel_run(run_id: str, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    try:
        r = cancel_agent_run(db, p, run_id)
    except LookupError:
        raise HTTPException(404, "Run not found")
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return {"id": r.id, "status": r.status}

@app.post("/api/v1/agent-runs/{run_id}/retry")
def retry_run(run_id: str, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    try:
        r = retry_agent_run(db, p, run_id)
    except LookupError:
        raise HTTPException(404, "Run not found")
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return {"id": r.id, "status": r.status}

@app.post("/api/v1/projects/{project_id}/knowledge/{document_id}/index")
def index_knowledge(project_id: str, document_id: str, p: Principal = Depends(principal),
                    db: Session = Depends(db_session)):
    try:
        count = index_document(db, p, project_id, document_id,
            db.execute(text("""SELECT content FROM ide_knowledge_documents
              WHERE id=:doc AND tenant_id=:tenant AND project_id=:project"""),
              {"doc": document_id, "tenant": p.tenant_id, "project": project_id}).scalar() or "")
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except LookupError:
        raise HTTPException(404, "Document not found")
    return {"chunks_indexed": count}

@app.post("/api/v1/projects/{project_id}/knowledge/vector-search")
def vector_knowledge(project_id: str, body: SearchIn, p: Principal = Depends(principal),
                     db: Session = Depends(db_session)):
    try:
        return {"matches": search_vectors(db, p, project_id, body.query)}
    except PermissionError as exc:
        raise HTTPException(403, str(exc))

from .phase22 import ToolRequest, AgentJob, ToolApproval, enqueue, request_tool, decide_tool

@app.post("/api/v1/agent-runs/{run_id}/enqueue")
def enqueue_agent_run(run_id: str, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    try:
        job=enqueue(db,p,run_id)
    except LookupError:
        raise HTTPException(404,"Run not found")
    except PermissionError as exc:
        raise HTTPException(403,str(exc))
    except ValueError as exc:
        raise HTTPException(409,str(exc))
    return {"job_id":job.id,"state":job.state,"execution_started":False}

@app.post("/api/v1/agent-runs/{run_id}/tool-requests", status_code=201)
def request_agent_tool(run_id: str, body: ToolRequest, p: Principal = Depends(principal),
                       db: Session = Depends(db_session)):
    try:
        item=request_tool(db,p,run_id,body)
    except LookupError:
        raise HTTPException(404,"Run not found")
    except PermissionError as exc:
        raise HTTPException(403,str(exc))
    except (ValueError,RuntimeError) as exc:
        raise HTTPException(400,str(exc))
    return {"id":item.id,"state":item.state,"args_sha256":item.args_sha256}

@app.post("/api/v1/tool-approvals/{approval_id}/decision")
def decide_agent_tool(approval_id: str, approved: bool, p: Principal = Depends(principal),
                      db: Session = Depends(db_session)):
    try:
        item=decide_tool(db,p,approval_id,approved)
    except LookupError:
        raise HTTPException(404,"Approval not found")
    except PermissionError as exc:
        raise HTTPException(403,str(exc))
    except ValueError as exc:
        raise HTTPException(409,str(exc))
    return {"id":item.id,"state":item.state}
