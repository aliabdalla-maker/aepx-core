"""Phase 1 hybrid IDE API: authenticated, tenant-scoped project metadata.

This service deliberately does not execute generated code or issue identity tokens.
Run behind TLS with a managed OIDC gateway in production.
"""
import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="AEP-X Hybrid IDE API", version="0.1.0")
DB_PATH = Path(os.getenv("IDE_DB_PATH", "/data/ide.sqlite3"))


def identity(x_ide_tenant: str | None = Header(default=None),
             x_ide_api_key: str | None = Header(default=None)) -> str:
    """Temporary development-only boundary. Replace with verified OIDC claims.

    A tenant header is NOT identity: require an independent secret and reject
    production deployment with this temporary authentication mode.
    """
    if os.getenv("IDE_ENV", "development") != "development":
        raise HTTPException(503, "OIDC integration required outside development")
    key = os.getenv("IDE_DEV_API_KEY", "")
    if not key or not x_ide_api_key:
        raise HTTPException(401, "Development API key required")
    import hmac
    if not hmac.compare_digest(key, x_ide_api_key):
        raise HTTPException(401, "Invalid development API key")
    if not x_ide_tenant or len(x_ide_tenant) > 128:
        raise HTTPException(400, "Tenant header required")
    return x_ide_tenant


@contextmanager
def database():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    try:
        connection.execute("""CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
            name TEXT NOT NULL, description TEXT NOT NULL DEFAULT ''
        )""")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_projects_tenant ON projects(tenant_id)"
        )
        yield connection
        connection.commit()
    finally:
        connection.close()


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)


class ProjectOut(ProjectIn):
    id: str


@app.get("/health")
def health():
    return {"status": "ok", "service": "hybrid-ide-api"}


@app.post("/api/v1/projects", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectIn, tenant: str = Depends(identity)):
    project_id = str(uuid.uuid4())
    with database() as db:
        db.execute(
            "INSERT INTO projects (id, tenant_id, name, description) VALUES (?, ?, ?, ?)",
            (project_id, tenant, body.name, body.description),
        )
    return ProjectOut(id=project_id, **body.model_dump())


@app.get("/api/v1/projects", response_model=list[ProjectOut])
def list_projects(tenant: str = Depends(identity)):
    with database() as db:
        rows = db.execute(
            "SELECT id, name, description FROM projects WHERE tenant_id = ? ORDER BY name",
            (tenant,),
        ).fetchall()
    return [ProjectOut(id=r[0], name=r[1], description=r[2]) for r in rows]


@app.get("/api/v1/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, tenant: str = Depends(identity)):
    with database() as db:
        row = db.execute(
            "SELECT id, name, description FROM projects WHERE id = ? AND tenant_id = ?",
            (project_id, tenant),
        ).fetchone()
    if row is None:
        raise HTTPException(404, "Project not found")
    return ProjectOut(id=row[0], name=row[1], description=row[2])
