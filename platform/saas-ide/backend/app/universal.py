"""Universal IDE platform routes: modules (§2-4), ACL and members (§5), CRUD lifecycle (§6).

Every mutating route checks the server-side ACL matrix, runs inside the caller's tenant
row-level-security scope, and appends to the tamper-evident audit chain in the same transaction.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from . import acl
from .main import Principal, db_session, principal, safe_path
from .modules import registry

router = APIRouter()


def audit(db: Session, p: Principal, action: str, kind: str, resource: str, detail: str = "") -> None:
    db.execute(text("SELECT ide_append_audit(:t,:a,:ac,:k,:r,:d)"),
               {"t": p.tenant_id, "a": p.subject, "ac": action, "k": kind, "r": resource, "d": detail})


def live_project(db: Session, p: Principal, project_id: str, archived: bool = False):
    row = db.execute(text("""SELECT id, name, description, module, archived_at FROM ide_projects
        WHERE tenant_id=:t AND id=:i"""), {"t": p.tenant_id, "i": project_id}).mappings().first()
    if row is None or (row["archived_at"] is not None) != archived:
        raise HTTPException(404, "Project not found")
    return row


def record_version(db: Session, p: Principal, project_id: str, path: str, op: str, content: str) -> int:
    version = db.execute(text("""SELECT COALESCE(MAX(version),0)+1 FROM ide_file_versions
        WHERE tenant_id=:t AND project_id=:p AND path=:f"""),
        {"t": p.tenant_id, "p": project_id, "f": path}).scalar()
    db.execute(text("""INSERT INTO ide_file_versions(tenant_id,project_id,path,version,op,content,author)
        VALUES (:t,:p,:f,:v,:op,:c,:a)"""), {"t": p.tenant_id, "p": project_id, "f": path,
        "v": version, "op": op, "c": content, "a": p.subject})
    return int(version)


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Concurrent change detected; reload and try again") from None


# --------------------------------------------------------------------------- modules (§2-4)
@router.get("/api/v1/ide-modules")
def ide_modules():
    """Public catalogue: available modules and the planned roadmap. No tenant data."""
    return registry()


# --------------------------------------------------------------------------- ACL (§5)
@router.get("/api/v1/acl/matrix")
def acl_matrix(p: Principal = Depends(principal)):
    return {"roles": acl.ROLES, "actions": acl.ACTIONS, "matrix": acl.matrix(),
            "media_paths": acl.MEDIA_PREFIXES}


@router.get("/api/v1/me/permissions")
def my_permissions(p: Principal = Depends(principal)):
    return {"role": p.role, "permissions": acl.matrix().get(p.role, {})}


class MemberIn(BaseModel):
    role: str = Field(pattern="^(owner|admin|editor|media_editor|reviewer|viewer|remove)$")


@router.get("/api/v1/members")
def list_members(p: Principal = Depends(principal), db: Session = Depends(db_session)):
    rows = db.execute(text("SELECT subject, role FROM ide_memberships WHERE tenant_id=:t ORDER BY role, subject"),
                      {"t": p.tenant_id}).mappings().all()
    return [dict(r) for r in rows]


@router.put("/api/v1/members/{subject}")
def set_member(subject: str, body: MemberIn, p: Principal = Depends(principal),
               db: Session = Depends(db_session)):
    acl.require(p.role, "manage_members", "workspace")
    try:
        db.execute(text("SELECT ide_set_member_role(:t,:a,:s,:r)"),
                   {"t": p.tenant_id, "a": p.subject, "s": subject, "r": body.role})
    except DBAPIError as exc:
        db.rollback()
        code = getattr(getattr(exc, "orig", None), "sqlstate", "")
        raise HTTPException(409 if code == "23514" else 403 if code == "42501" else 400,
                            str(getattr(exc, "orig", exc)).split("\n")[0][:200]) from None
    audit(db, p, "member." + body.role, "member", subject)
    db.commit()
    return {"subject": subject, "role": body.role}


# --------------------------------------------------------------------------- projects (§6)
class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


@router.patch("/api/v1/projects/{project_id}")
def update_project(project_id: str, body: ProjectPatch, p: Principal = Depends(principal),
                   db: Session = Depends(db_session)):
    acl.require(p.role, "edit", "project")
    row = live_project(db, p, project_id)
    name = body.name if body.name is not None else row["name"]
    description = body.description if body.description is not None else row["description"]
    db.execute(text("UPDATE ide_projects SET name=:n, description=:d WHERE tenant_id=:t AND id=:i"),
               {"n": name, "d": description, "t": p.tenant_id, "i": project_id})
    audit(db, p, "project.update", "project", project_id)
    db.commit()
    return {"id": project_id, "name": name, "description": description, "module": row["module"]}


@router.delete("/api/v1/projects/{project_id}")
def archive_project(project_id: str, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    """Safe deletion: projects are archived and can be restored; nothing is destroyed."""
    acl.require(p.role, "delete", "project")
    live_project(db, p, project_id)
    db.execute(text("UPDATE ide_projects SET archived_at=now() WHERE tenant_id=:t AND id=:i"),
               {"t": p.tenant_id, "i": project_id})
    audit(db, p, "project.archive", "project", project_id)
    db.commit()
    return {"id": project_id, "archived": True}


@router.get("/api/v1/projects-archived")
def archived_projects(p: Principal = Depends(principal), db: Session = Depends(db_session)):
    rows = db.execute(text("""SELECT id, name, description, module, archived_at FROM ide_projects
        WHERE tenant_id=:t AND archived_at IS NOT NULL ORDER BY archived_at DESC"""),
        {"t": p.tenant_id}).mappings().all()
    return [{**dict(r), "archived_at": r["archived_at"].isoformat()} for r in rows]


@router.post("/api/v1/projects/{project_id}/restore")
def restore_project(project_id: str, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    acl.require(p.role, "delete", "project")
    live_project(db, p, project_id, archived=True)
    db.execute(text("UPDATE ide_projects SET archived_at=NULL WHERE tenant_id=:t AND id=:i"),
               {"t": p.tenant_id, "i": project_id})
    audit(db, p, "project.restore", "project", project_id)
    db.commit()
    return {"id": project_id, "archived": False}


# --------------------------------------------------------------------------- files (§6)
@router.delete("/api/v1/projects/{project_id}/files/{path:path}")
def delete_file(project_id: str, path: str, p: Principal = Depends(principal),
                db: Session = Depends(db_session)):
    path = safe_path(path)
    acl.require(p.role, "delete", "file", path)
    live_project(db, p, project_id)
    row = db.execute(text("""DELETE FROM ide_workspace_files WHERE tenant_id=:t AND project_id=:p AND path=:f
        RETURNING content"""), {"t": p.tenant_id, "p": project_id, "f": path}).first()
    if row is None:
        db.rollback()
        raise HTTPException(404, "File not found")
    version = record_version(db, p, project_id, path, "delete", row.content)
    audit(db, p, "file.delete", "file", f"{project_id}/{path}", f"version {version}")
    _commit(db)
    return {"path": path, "deleted": True, "version": version}


class MoveIn(BaseModel):
    from_path: str = Field(min_length=1, max_length=255)
    to_path: str = Field(min_length=1, max_length=255)


MAX_TREE_FILES = 2000


def _tree(db: Session, p: Principal, project_id: str, path: str):
    """The file at `path` plus every file under the folder `path/` (prefix compare, no LIKE)."""
    return db.execute(text("""SELECT path, content FROM ide_workspace_files
        WHERE tenant_id=:t AND project_id=:p AND (path=:f OR left(path, :n) = :prefix)
        ORDER BY path"""), {"t": p.tenant_id, "p": project_id, "f": path,
                             "n": len(path) + 1, "prefix": path + "/"}).all()


@router.post("/api/v1/projects/{project_id}/files-move")
def move_files(project_id: str, body: MoveIn, p: Principal = Depends(principal),
               db: Session = Depends(db_session)):
    """Rename or move a file, or a whole folder. All-or-nothing; history is kept on both paths."""
    src, dst = safe_path(body.from_path), safe_path(body.to_path)
    if src == dst:
        raise HTTPException(400, "The new name is the same as the old one")
    if dst.startswith(src + "/"):
        raise HTTPException(400, "A folder cannot be moved into itself")
    live_project(db, p, project_id)
    rows = _tree(db, p, project_id, src)
    if not rows:
        db.rollback()
        raise HTTPException(404, "File or folder not found")
    if len(rows) > MAX_TREE_FILES:
        db.rollback()
        raise HTTPException(400, f"Folders with more than {MAX_TREE_FILES} files cannot be moved in one step")
    moves = [(r.path, dst + r.path[len(src):], r.content) for r in rows]
    for old, new, _ in moves:
        safe_path(new)
        acl.require(p.role, "delete", "file", old)
        acl.require(p.role, "create", "file", new)
    moving = {old for old, _, _ in moves}
    clash = db.execute(text("""SELECT path FROM ide_workspace_files
        WHERE tenant_id=:t AND project_id=:p AND path = ANY(:paths)"""),
        {"t": p.tenant_id, "p": project_id, "paths": [n for _, n, _ in moves]}).scalars().all()
    clash = [c for c in clash if c not in moving]
    if clash:
        db.rollback()
        raise HTTPException(409, "These files already exist: " + ", ".join(clash[:5]))
    # Delete then insert inside one transaction, so overlapping old/new paths never collide.
    for old, _, content in moves:
        db.execute(text("DELETE FROM ide_workspace_files WHERE tenant_id=:t AND project_id=:p AND path=:f"),
                   {"t": p.tenant_id, "p": project_id, "f": old})
        record_version(db, p, project_id, old, "delete", content)
    for _, new, content in moves:
        db.execute(text("""INSERT INTO ide_workspace_files(tenant_id, project_id, path, content)
            VALUES (:t, :p, :f, :c)"""), {"t": p.tenant_id, "p": project_id, "f": new, "c": content})
        record_version(db, p, project_id, new, "save", content)
    audit(db, p, "file.move", "file", f"{project_id}/{src}", f"to {dst} ({len(moves)} file{'s' if len(moves) != 1 else ''})")
    _commit(db)
    return {"moved": [{"from": o, "to": n} for o, n, _ in moves], "count": len(moves)}


@router.delete("/api/v1/projects/{project_id}/folders/{path:path}")
def delete_folder(project_id: str, path: str, p: Principal = Depends(principal),
                  db: Session = Depends(db_session)):
    """Delete every file in a folder. Each file keeps its history and can be restored."""
    path = safe_path(path)
    live_project(db, p, project_id)
    rows = [r for r in _tree(db, p, project_id, path) if r.path != path]
    if not rows:
        db.rollback()
        raise HTTPException(404, "Folder not found or empty")
    for r in rows:
        acl.require(p.role, "delete", "file", r.path)
    for r in rows:
        db.execute(text("DELETE FROM ide_workspace_files WHERE tenant_id=:t AND project_id=:p AND path=:f"),
                   {"t": p.tenant_id, "p": project_id, "f": r.path})
        record_version(db, p, project_id, r.path, "delete", r.content)
    audit(db, p, "folder.delete", "file", f"{project_id}/{path}/", f"{len(rows)} files")
    _commit(db)
    return {"folder": path, "deleted": len(rows)}


@router.get("/api/v1/projects/{project_id}/history")
def file_history(project_id: str, path: str, p: Principal = Depends(principal),
                 db: Session = Depends(db_session)):
    path = safe_path(path)
    live_project(db, p, project_id)
    rows = db.execute(text("""SELECT version, op, author, created_at, length(content) AS size
        FROM ide_file_versions WHERE tenant_id=:t AND project_id=:p AND path=:f
        ORDER BY version DESC LIMIT 100"""), {"t": p.tenant_id, "p": project_id, "f": path}).mappings().all()
    return [{**dict(r), "created_at": r["created_at"].isoformat()} for r in rows]


@router.get("/api/v1/projects/{project_id}/history/{version}")
def file_version(project_id: str, version: int, path: str, p: Principal = Depends(principal),
                 db: Session = Depends(db_session)):
    path = safe_path(path)
    live_project(db, p, project_id)
    row = db.execute(text("""SELECT version, op, content FROM ide_file_versions
        WHERE tenant_id=:t AND project_id=:p AND path=:f AND version=:v"""),
        {"t": p.tenant_id, "p": project_id, "f": path, "v": version}).mappings().first()
    if row is None:
        raise HTTPException(404, "Version not found")
    return dict(row)


class RestoreIn(BaseModel):
    path: str = Field(min_length=1, max_length=255)
    version: int = Field(ge=1)


@router.post("/api/v1/projects/{project_id}/restore-file")
def restore_file(project_id: str, body: RestoreIn, p: Principal = Depends(principal),
                 db: Session = Depends(db_session)):
    path = safe_path(body.path)
    acl.require(p.role, "edit", "file", path)
    live_project(db, p, project_id)
    row = db.execute(text("""SELECT content FROM ide_file_versions
        WHERE tenant_id=:t AND project_id=:p AND path=:f AND version=:v"""),
        {"t": p.tenant_id, "p": project_id, "f": path, "v": body.version}).first()
    if row is None:
        raise HTTPException(404, "Version not found")
    db.execute(text("""INSERT INTO ide_workspace_files(tenant_id,project_id,path,content) VALUES (:t,:p,:f,:c)
        ON CONFLICT (tenant_id,project_id,path) DO UPDATE SET content=EXCLUDED.content"""),
        {"t": p.tenant_id, "p": project_id, "f": path, "c": row.content})
    version = record_version(db, p, project_id, path, "restore", row.content)
    audit(db, p, "file.restore", "file", f"{project_id}/{path}", f"from {body.version} as {version}")
    _commit(db)
    return {"path": path, "content": row.content, "version": version}


# --------------------------------------------------------------------------- audit (§5)
@router.get("/api/v1/audit-events")
def audit_events(limit: int = 100, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    if p.role not in ("owner", "admin", "reviewer"):
        raise HTTPException(403, "Owners, admins and reviewers can read the audit trail")
    rows = db.execute(text("""SELECT id, actor, action, resource_type, resource_id, detail, hash, created_at
        FROM ide_audit_events WHERE tenant_id=:t ORDER BY id DESC LIMIT :l"""),
        {"t": p.tenant_id, "l": max(1, min(limit, 500))}).mappings().all()
    return [{**dict(r), "created_at": r["created_at"].isoformat()} for r in rows]


@router.get("/api/v1/audit-events/verify")
def verify_audit(p: Principal = Depends(principal), db: Session = Depends(db_session)):
    if p.role not in ("owner", "admin", "reviewer"):
        raise HTTPException(403, "Owners, admins and reviewers can verify the audit trail")
    broken = db.execute(text("SELECT ide_verify_audit(:t)"), {"t": p.tenant_id}).scalar()
    return {"intact": broken is None, "first_broken_event": broken}
