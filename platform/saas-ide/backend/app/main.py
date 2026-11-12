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
SessionLocal = sessionmaker(bind=engine)
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
