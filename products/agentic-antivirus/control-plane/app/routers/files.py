"""Virtual file system: tenant-isolated file and folder CRUD with security controls.

Trace: VFS-01..17, FN-08, FN-09, S2 step 6. Used for incident evidence, exports and documents.

Storage: content-addressed blobs under AAV_FILE_STORE_DIR/<tenant>/<sha256>, written via a
temporary file, size-capped while streaming, hashed, MIME-sniffed and malware-scanned before
the version row is committed. Infected uploads are rejected and audited.
"""
from __future__ import annotations

import csv
import io
import json
import os
import tarfile
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app import audit, db, file_handlers as fh
from app.config import settings
from app.deps import Principal, need

router = APIRouter(prefix="/v1/files", tags=["files"])

# (signature bytes, offset, mime)
_MAGIC = [
    (b"%PDF-", 0, "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", 0, "image/png"),
    (b"\xff\xd8\xff", 0, "image/jpeg"),
    (b"GIF87a", 0, "image/gif"), (b"GIF89a", 0, "image/gif"),
    (b"RIFF", 0, "riff"),
    (b"PK\x03\x04", 0, "application/zip"),
    (b"\x1f\x8b", 0, "application/gzip"),
    (b"ustar", 257, "application/x-tar"),
    (b"ID3", 0, "audio/mpeg"), (b"OggS", 0, "audio/ogg"), (b"fLaC", 0, "audio/flac"),
    (b"ftyp", 4, "video/mp4"),
    (b"\x1aE\xdf\xa3", 0, "video/webm"),
    (b"MZ", 0, "application/x-msdownload"),
    (b"\x7fELF", 0, "application/x-elf"),
]
TEXT_EXT = {".txt": "text/plain", ".csv": "text/csv", ".json": "application/json", ".xml": "application/xml",
            ".md": "text/markdown", ".log": "text/plain"}
OFFICE_EXT = {".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
              ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
              ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation"}

# Capability matrix (DLV-19, VFS-07/08). 'verified' means covered by tests (test_files.py, test_file_handlers.py).
# Preview of PDF, images, audio and video = served inline to the browser's sandboxed viewer/player; Office and
# archive preview = structured JSON extracted server-side without rendering or extracting anything (file_handlers).
_TEXT = {"store": True, "preview": True, "edit": True, "verified": True}
_INLINE = {"store": True, "preview": True, "edit": False, "convert": [], "verified": True}
HANDLERS = {
    "text/plain": {**_TEXT, "convert": []},
    "text/markdown": {**_TEXT, "convert": []},
    "text/csv": {**_TEXT, "convert": ["application/json"]},
    "application/json": {**_TEXT, "convert": ["text/csv"]},
    "application/xml": {**_TEXT, "convert": []},
    "image/png": dict(_INLINE), "image/jpeg": dict(_INLINE), "image/gif": dict(_INLINE), "image/webp": dict(_INLINE),
    "application/pdf": {**_INLINE, "note": "inline in the browser's PDF viewer; deny-all CSP"},
    "application/zip": {**_INLINE, "note": "preview = entry listing; bulk import/export supported"},
    "application/x-tar": {**_INLINE, "note": "preview = entry listing"},
    "application/gzip": {**_INLINE, "note": "preview = entry listing"},
    fh.DOCX: {**_INLINE, "convert": ["text/plain"], "note": "preview = extracted text"},
    fh.XLSX: {**_INLINE, "convert": ["text/csv"], "note": "preview = sheets and cells; convert = first sheet"},
    fh.PPTX: {**_INLINE, "convert": ["text/plain"], "note": "preview = slide text"},
}
for m in ("audio/mpeg", "audio/ogg", "audio/flac", "audio/wav", "video/mp4", "video/webm"):
    HANDLERS[m] = {**_INLINE, "note": "inline in the browser's media player (range requests)"}
OPAQUE = {"store": True, "preview": False, "edit": False, "convert": [], "verified": True, "note": "opaque blob"}


def sniff(head: bytes, filename: str) -> str:
    for sig, off, mime in _MAGIC:
        if head[off:off + len(sig)] == sig:
            if mime == "riff":
                return {b"WEBP": "image/webp", b"WAVE": "audio/wav", b"AVI ": "video/x-msvideo"}.get(head[8:12],
                                                                                                    "application/octet-stream")
            if mime == "application/zip":
                ext = PurePosixPath(filename).suffix.lower()
                return OFFICE_EXT.get(ext, mime)
            return mime
    ext = PurePosixPath(filename).suffix.lower()
    if ext in TEXT_EXT:
        try:
            head.decode("utf-8")
            return TEXT_EXT[ext]
        except UnicodeDecodeError:
            pass
    try:
        head.decode("utf-8")
        if b"\x00" not in head:
            return "text/plain"
    except UnicodeDecodeError:
        pass
    return "application/octet-stream"


def _engine():
    from app.detections import current_engine
    return current_engine()


def _tenant_dir(tenant_id) -> Path:
    d = Path(settings.file_store_dir) / str(tenant_id)
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    return d


def _check_name(name: str) -> str:
    if not name or name in (".", "..") or "/" in name or "\\" in name or "\x00" in name or len(name) > 255:
        raise HTTPException(422, "invalid name")
    return name


def _usage(cur) -> int:
    # blobs are content-addressed per tenant, so each distinct sha256 is stored once
    cur.execute("SELECT COALESCE(sum(blob_size), 0) AS n FROM (SELECT DISTINCT ON (sha256) size_bytes AS blob_size "
                "FROM aav.vfs_versions) s")
    return int(cur.fetchone()["n"])


def _store_stream(tenant_id, chunks, filename: str) -> dict:
    """Stream to a temp file with size cap; hash; sniff; scan. Returns blob metadata."""
    import hashlib
    tdir = _tenant_dir(tenant_id)
    h = hashlib.sha256()
    size = 0
    head = b""
    fd, tmp = tempfile.mkstemp(dir=tdir, prefix=".upload-")
    try:
        with os.fdopen(fd, "wb") as out:
            for chunk in chunks:
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise HTTPException(413, f"file exceeds {settings.max_upload_bytes} bytes")
                if len(head) < 512:
                    head += chunk[:512 - len(head)]
                h.update(chunk)
                out.write(chunk)
        sha = h.hexdigest()
        mime = sniff(head, filename)
        engine = _engine()
        verdict = None
        if engine is not None:
            _, verdict = engine.scan_file(tmp)
            scan = {"engine_version": engine.version, "clean": verdict is None,
                    "detection": verdict.__dict__ if verdict else None}
        else:
            scan = {"engine_version": None, "clean": None, "detection": None, "error": "no detection bundle published"}
        status = "infected" if verdict else ("clean" if engine is not None else "error")
        if status != "clean":
            os.unlink(tmp)
            return {"sha256": sha, "size": size, "mime": mime, "scan_status": status, "scan": scan, "key": None}
        final = tdir / sha
        if final.exists():
            os.unlink(tmp)
        else:
            os.replace(tmp, final)
            os.chmod(final, 0o600)
        return {"sha256": sha, "size": size, "mime": mime, "scan_status": "clean", "scan": scan, "key": sha}
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


class NodeIn(BaseModel):
    name: str
    parent_id: UUID | None = None


class NodePatch(BaseModel):
    name: str | None = None
    parent_id: UUID | None = None
    move_to_root: bool = False


class CopyIn(BaseModel):
    target_parent_id: UUID | None = None


class RetentionIn(BaseModel):
    days: int = Field(ge=0, le=3650)


class TextEditIn(BaseModel):
    content: str = Field(max_length=10 * 1024 * 1024)


def _get_node(cur, node_id, *, live=True) -> dict:
    cur.execute("SELECT * FROM aav.vfs_nodes WHERE id = %s" + (" AND trashed_at IS NULL" if live else ""), (node_id,))
    n = cur.fetchone()
    if not n:
        raise HTTPException(404, "not found")
    return n


def _ensure_dir(cur, parent_id):
    if parent_id is None:
        return
    n = _get_node(cur, parent_id)
    if n["kind"] != "dir":
        raise HTTPException(422, "parent is not a folder")


def _is_descendant(cur, node_id, maybe_child) -> bool:
    cur.execute("WITH RECURSIVE t AS (SELECT id FROM aav.vfs_nodes WHERE id = %s UNION ALL "
                "SELECT n.id FROM aav.vfs_nodes n JOIN t ON n.parent_id = t.id) SELECT 1 FROM t WHERE id = %s",
                (node_id, maybe_child))
    return cur.fetchone() is not None


def _add_version(cur, p: Principal, node_id, blob: dict) -> int:
    cur.execute("SELECT COALESCE(max(version), 0) + 1 AS v FROM aav.vfs_versions WHERE node_id = %s", (node_id,))
    v = cur.fetchone()["v"]
    cur.execute("INSERT INTO aav.vfs_versions (tenant_id, node_id, version, sha256, size_bytes, mime, storage_key, "
                "scan_status, scan_detail, created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (p.tenant_id, node_id, v, blob["sha256"], blob["size"], blob["mime"], blob["key"], "clean",
                 json.dumps(blob["scan"], default=str), p.user_id))
    cur.execute("UPDATE aav.vfs_nodes SET current_version = %s, updated_at = now() WHERE id = %s", (v, node_id))
    return v


@router.get("/handlers")
def handlers(p: Principal = Depends(need("files.read"))):
    return {"handlers": HANDLERS, "default": OPAQUE}


@router.get("")
def list_nodes(parent_id: UUID | None = None, q: str | None = None, sort: str = "name", order: str = "asc",
               kind: str | None = None, mime: str | None = None, trashed: bool = False, limit: int = 200,
               offset: int = 0, p: Principal = Depends(need("files.read"))):
    if sort not in ("name", "updated_at", "created_at", "size_bytes"):
        raise HTTPException(422, "invalid sort")
    direction = "DESC" if order == "desc" else "ASC"
    limit = max(1, min(limit, 1000))
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute(
            "SELECT n.id, n.parent_id, n.name, n.kind, n.current_version, n.trashed_at, n.retain_until, n.created_at, "
            "n.updated_at, v.size_bytes, v.mime, v.sha256 FROM aav.vfs_nodes n LEFT JOIN aav.vfs_versions v "
            "ON v.node_id = n.id AND v.version = n.current_version WHERE "
            "(CASE WHEN %s::text IS NOT NULL THEN true ELSE n.parent_id IS NOT DISTINCT FROM %s END) "
            "AND (%s::text IS NULL OR n.name ILIKE '%%' || %s || '%%') AND (%s::text IS NULL OR n.kind = %s) "
            "AND (%s::text IS NULL OR v.mime = %s) AND ((n.trashed_at IS NOT NULL) = %s) "
            f"ORDER BY n.kind, {'v.' if sort == 'size_bytes' else 'n.'}{sort} {direction} NULLS LAST LIMIT %s OFFSET %s",
            (q, parent_id, q, q, kind, kind, mime, mime, trashed, limit, offset))
        return cur.fetchall()


@router.post("/folders", status_code=201)
def create_folder(body: NodeIn, p: Principal = Depends(need("files.write"))):
    _check_name(body.name)
    with db.tenant_tx(p.tenant_id) as cur:
        _ensure_dir(cur, body.parent_id)
        try:
            cur.execute("INSERT INTO aav.vfs_nodes (tenant_id, parent_id, name, kind, created_by) VALUES "
                        "(%s,%s,%s,'dir',%s) RETURNING id", (p.tenant_id, body.parent_id, body.name, p.user_id))
        except Exception as exc:
            if "vfs_unique_live_name" in str(exc):
                raise HTTPException(409, "name already exists")
            raise
        nid = cur.fetchone()["id"]
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="file.mkdir", target=str(nid),
                     detail={"name": body.name})
    return {"id": str(nid)}


@router.post("/upload", status_code=201)
async def upload(file: UploadFile, parent_id: UUID | None = None, p: Principal = Depends(need("files.write"))):
    name = _check_name(os.path.basename(file.filename or ""))

    def chunks():
        while True:
            b = file.file.read(1024 * 1024)
            if not b:
                break
            yield b

    with db.tenant_tx(p.tenant_id) as cur:
        _ensure_dir(cur, parent_id)
        used = _usage(cur)
    blob = _store_stream(p.tenant_id, chunks(), name)
    with db.tenant_tx(p.tenant_id) as cur:
        if blob["scan_status"] != "clean":
            audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="file.upload_rejected", target=name,
                         detail={"sha256": blob["sha256"], "scan": blob["scan"]})
            cur.connection.commit()
            raise HTTPException(422, {"error": "upload rejected", "scan_status": blob["scan_status"],
                                      "scan": blob["scan"]})
        if used + blob["size"] > settings.tenant_quota_bytes:
            audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="file.quota_exceeded", target=name)
            cur.connection.commit()
            raise HTTPException(507, "tenant storage quota exceeded")
        cur.execute("SELECT id, kind FROM aav.vfs_nodes WHERE parent_id IS NOT DISTINCT FROM %s AND name = %s "
                    "AND trashed_at IS NULL", (parent_id, name))
        existing = cur.fetchone()
        if existing and existing["kind"] == "dir":
            raise HTTPException(409, "a folder with that name exists")
        if existing:
            nid = existing["id"]
        else:
            cur.execute("INSERT INTO aav.vfs_nodes (tenant_id, parent_id, name, kind, created_by) VALUES "
                        "(%s,%s,%s,'file',%s) RETURNING id", (p.tenant_id, parent_id, name, p.user_id))
            nid = cur.fetchone()["id"]
        v = _add_version(cur, p, nid, blob)
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="file.upload", target=str(nid),
                     detail={"name": name, "version": v, "sha256": blob["sha256"], "size": blob["size"],
                             "mime": blob["mime"]})
    return {"id": str(nid), "version": v, "sha256": blob["sha256"], "mime": blob["mime"], "size": blob["size"]}


def _blob_path(tenant_id, key: str) -> Path:
    path = (_tenant_dir(tenant_id) / key).resolve()
    if path.parent != _tenant_dir(tenant_id).resolve() or path.is_symlink():
        raise HTTPException(500, "storage integrity error")
    return path


@router.get("/{node_id}/download")
def download(node_id: UUID, version: int | None = None, p: Principal = Depends(need("files.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        n = _get_node(cur, node_id)
        if n["kind"] != "file":
            raise HTTPException(422, "folders are exported with /export")
        cur.execute("SELECT * FROM aav.vfs_versions WHERE node_id = %s AND version = %s",
                    (node_id, version or n["current_version"]))
        v = cur.fetchone()
        if not v:
            raise HTTPException(404, "version not found")
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="file.download", target=str(node_id),
                     detail={"version": v["version"]})
    return FileResponse(_blob_path(p.tenant_id, v["storage_key"]), media_type="application/octet-stream",
                        filename=n["name"], headers={"X-Content-Type-Options": "nosniff",
                                                     "Content-Security-Policy": "sandbox",
                                                     "X-Checksum-SHA256": v["sha256"]})


@router.get("/{node_id}/preview")
def preview(node_id: UUID, p: Principal = Depends(need("files.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        n = _get_node(cur, node_id)
        cur.execute("SELECT * FROM aav.vfs_versions WHERE node_id = %s AND version = %s", (node_id, n["current_version"]))
        v = cur.fetchone()
    if not v or not HANDLERS.get(v["mime"], OPAQUE)["preview"]:
        raise HTTPException(415, "no verified preview handler for this format")
    path = _blob_path(p.tenant_id, v["storage_key"])
    if fh.inline_media(v["mime"]):
        return FileResponse(path, media_type=v["mime"], headers=fh.inline_headers(v["mime"]))
    if v["mime"] in fh.OFFICE or v["mime"] in fh.ARCHIVES:
        try:
            return fh.preview(path, v["mime"])
        except fh.HandlerError as exc:
            raise HTTPException(422, f"cannot preview: {exc}")
    with open(path, "rb") as fh_:
        text = fh_.read(1024 * 1024).decode("utf-8", errors="replace")
    return {"mime": v["mime"], "truncated": v["size_bytes"] > 1024 * 1024, "text": text}


@router.put("/{node_id}/content")
def edit_text(node_id: UUID, body: TextEditIn, p: Principal = Depends(need("files.write"))):
    with db.tenant_tx(p.tenant_id) as cur:
        n = _get_node(cur, node_id)
        cur.execute("SELECT mime FROM aav.vfs_versions WHERE node_id = %s AND version = %s", (node_id, n["current_version"]))
        v = cur.fetchone()
    if not v or not HANDLERS.get(v["mime"], OPAQUE)["edit"]:
        raise HTTPException(415, "no verified edit handler for this format")
    if v["mime"] == "application/json":
        try:
            json.loads(body.content)
        except ValueError:
            raise HTTPException(422, "invalid JSON")
    blob = _store_stream(p.tenant_id, [body.content.encode()], n["name"])
    if blob["scan_status"] != "clean":
        raise HTTPException(422, {"error": "content rejected", "scan": blob["scan"]})
    with db.tenant_tx(p.tenant_id) as cur:
        ver = _add_version(cur, p, node_id, blob)
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="file.edit", target=str(node_id),
                     detail={"version": ver, "sha256": blob["sha256"]})
    return {"version": ver, "sha256": blob["sha256"]}


@router.post("/{node_id}/convert")
def convert(node_id: UUID, to: str = Query(...), p: Principal = Depends(need("files.write"))):
    with db.tenant_tx(p.tenant_id) as cur:
        n = _get_node(cur, node_id)
        cur.execute("SELECT * FROM aav.vfs_versions WHERE node_id = %s AND version = %s", (node_id, n["current_version"]))
        v = cur.fetchone()
    if not v or to not in HANDLERS.get(v["mime"], OPAQUE)["convert"]:
        raise HTTPException(415, "conversion not supported")
    ext = {"text/plain": ".txt", "text/csv": ".csv", "application/json": ".json"}
    if v["mime"] in fh.OFFICE:
        try:
            out, new_name = fh.convert(_blob_path(p.tenant_id, v["storage_key"]), v["mime"], to).decode(), \
                Path(n["name"]).stem + ext[to]
        except fh.HandlerError as exc:
            raise HTTPException(422, f"cannot convert: {exc}")
        return _save_converted(p, n, node_id, to, out, new_name)
    raw = _blob_path(p.tenant_id, v["storage_key"]).read_text(encoding="utf-8")
    if v["mime"] == "text/csv" and to == "application/json":
        out, new_name = json.dumps(list(csv.DictReader(io.StringIO(raw))), indent=2), Path(n["name"]).stem + ".json"
    else:
        data = json.loads(raw)
        if not (isinstance(data, list) and all(isinstance(r, dict) for r in data)):
            raise HTTPException(422, "JSON must be an array of objects to convert to CSV")
        cols = sorted({k for r in data for k in r})
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=cols)
        w.writeheader()
        w.writerows(data)
        out, new_name = buf.getvalue(), Path(n["name"]).stem + ".csv"
    return _save_converted(p, n, node_id, to, out, new_name)


def _save_converted(p: Principal, n: dict, node_id, to: str, out: str, new_name: str) -> dict:
    blob = _store_stream(p.tenant_id, [out.encode()], new_name)
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("SELECT 1 FROM aav.vfs_nodes WHERE parent_id IS NOT DISTINCT FROM %s AND name = %s AND trashed_at "
                    "IS NULL", (n["parent_id"], new_name))
        if cur.fetchone():
            raise HTTPException(409, f"{new_name} already exists")
        cur.execute("INSERT INTO aav.vfs_nodes (tenant_id, parent_id, name, kind, created_by) VALUES (%s,%s,%s,'file',%s) "
                    "RETURNING id", (p.tenant_id, n["parent_id"], new_name, p.user_id))
        nid = cur.fetchone()["id"]
        _add_version(cur, p, nid, blob)
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="file.convert", target=str(nid),
                     detail={"from": str(node_id), "to": to})
    return {"id": str(nid), "name": new_name}


@router.patch("/{node_id}")
def rename_move(node_id: UUID, body: NodePatch, p: Principal = Depends(need("files.write"))):
    with db.tenant_tx(p.tenant_id) as cur:
        n = _get_node(cur, node_id)
        new_parent = None if body.move_to_root else (body.parent_id if body.parent_id is not None else n["parent_id"])
        new_name = _check_name(body.name) if body.name else n["name"]
        _ensure_dir(cur, new_parent)
        if new_parent and _is_descendant(cur, node_id, new_parent):
            raise HTTPException(422, "cannot move a folder into itself")
        try:
            cur.execute("UPDATE aav.vfs_nodes SET name = %s, parent_id = %s, updated_at = now() WHERE id = %s",
                        (new_name, new_parent, node_id))
        except Exception as exc:
            if "vfs_unique_live_name" in str(exc):
                raise HTTPException(409, "name already exists")
            raise
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="file.rename_move", target=str(node_id),
                     detail={"name": new_name, "parent_id": str(new_parent) if new_parent else None})
    return {"id": str(node_id)}


def _copy_tree(cur, p: Principal, src_id, dest_parent) -> UUID:
    src = _get_node(cur, src_id)
    name = src["name"]
    cur.execute("SELECT 1 FROM aav.vfs_nodes WHERE parent_id IS NOT DISTINCT FROM %s AND name = %s AND trashed_at IS NULL",
                (dest_parent, name))
    if cur.fetchone():
        name = f"{Path(name).stem} (copy){Path(name).suffix}"
    cur.execute("INSERT INTO aav.vfs_nodes (tenant_id, parent_id, name, kind, current_version, created_by) "
                "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id", (p.tenant_id, dest_parent, name, src["kind"],
                                                             1 if src["kind"] == "file" else None, p.user_id))
    new_id = cur.fetchone()["id"]
    if src["kind"] == "file":
        cur.execute("INSERT INTO aav.vfs_versions (tenant_id, node_id, version, sha256, size_bytes, mime, storage_key, "
                    "scan_status, scan_detail, created_by) SELECT tenant_id, %s, 1, sha256, size_bytes, mime, storage_key, "
                    "scan_status, scan_detail, %s FROM aav.vfs_versions WHERE node_id = %s AND version = %s",
                    (new_id, p.user_id, src_id, src["current_version"]))
    else:
        cur.execute("SELECT id FROM aav.vfs_nodes WHERE parent_id = %s AND trashed_at IS NULL", (src_id,))
        for child in cur.fetchall():
            _copy_tree(cur, p, child["id"], new_id)
    return new_id


@router.post("/{node_id}/copy", status_code=201)
def copy(node_id: UUID, body: CopyIn, p: Principal = Depends(need("files.write"))):
    with db.tenant_tx(p.tenant_id) as cur:
        _ensure_dir(cur, body.target_parent_id)
        if body.target_parent_id and _is_descendant(cur, node_id, body.target_parent_id):
            raise HTTPException(422, "cannot copy a folder into itself")
        new_id = _copy_tree(cur, p, node_id, body.target_parent_id)
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="file.copy", target=str(new_id),
                     detail={"from": str(node_id)})
    return {"id": str(new_id)}


@router.delete("/{node_id}")
def trash(node_id: UUID, p: Principal = Depends(need("files.write"))):
    with db.tenant_tx(p.tenant_id) as cur:
        _get_node(cur, node_id)
        cur.execute("WITH RECURSIVE t AS (SELECT id FROM aav.vfs_nodes WHERE id = %s UNION ALL SELECT n.id FROM "
                    "aav.vfs_nodes n JOIN t ON n.parent_id = t.id) UPDATE aav.vfs_nodes SET trashed_at = now() "
                    "WHERE id IN (SELECT id FROM t) AND trashed_at IS NULL", (node_id,))
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="file.trash", target=str(node_id))
    return {"trashed": True}


@router.post("/{node_id}/restore")
def restore(node_id: UUID, p: Principal = Depends(need("files.write"))):
    with db.tenant_tx(p.tenant_id) as cur:
        n = _get_node(cur, node_id, live=False)
        if n["trashed_at"] is None:
            raise HTTPException(409, "not in trash")
        cur.execute("SELECT 1 FROM aav.vfs_nodes WHERE parent_id IS NOT DISTINCT FROM %s AND name = %s AND "
                    "trashed_at IS NULL", (n["parent_id"], n["name"]))
        if cur.fetchone():
            raise HTTPException(409, "an item with that name exists; rename it first")
        if n["parent_id"]:
            cur.execute("SELECT trashed_at FROM aav.vfs_nodes WHERE id = %s", (n["parent_id"],))
            if cur.fetchone()["trashed_at"] is not None:
                raise HTTPException(409, "restore the parent folder first")
        cur.execute("WITH RECURSIVE t AS (SELECT id FROM aav.vfs_nodes WHERE id = %s UNION ALL SELECT n.id FROM "
                    "aav.vfs_nodes n JOIN t ON n.parent_id = t.id) UPDATE aav.vfs_nodes SET trashed_at = NULL "
                    "WHERE id IN (SELECT id FROM t) AND trashed_at >= %s", (node_id, n["trashed_at"]))
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="file.restore", target=str(node_id))
    return {"restored": True}


@router.delete("/{node_id}/purge")
def purge(node_id: UUID, p: Principal = Depends(need("files.write"))):
    with db.tenant_tx(p.tenant_id) as cur:
        n = _get_node(cur, node_id, live=False)
        if n["trashed_at"] is None:
            raise HTTPException(409, "move to trash first")
        if n["retain_until"] and n["retain_until"] > datetime.now(timezone.utc):
            raise HTTPException(423, f"retained until {n['retain_until'].isoformat()}")
        cur.execute("DELETE FROM aav.vfs_nodes WHERE id = %s", (node_id,))
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="file.purge", target=str(node_id))
    return {"purged": True}


@router.put("/{node_id}/retention")
def set_retention(node_id: UUID, body: RetentionIn, p: Principal = Depends(need("settings.write"))):
    until = datetime.now(timezone.utc) + timedelta(days=body.days) if body.days else None
    with db.tenant_tx(p.tenant_id) as cur:
        _get_node(cur, node_id, live=False)
        cur.execute("UPDATE aav.vfs_nodes SET retain_until = %s WHERE id = %s", (until, node_id))
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="file.retention", target=str(node_id),
                     detail={"retain_until": until.isoformat() if until else None})
    return {"retain_until": until.isoformat() if until else None}


@router.get("/{node_id}/versions")
def versions(node_id: UUID, p: Principal = Depends(need("files.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        _get_node(cur, node_id, live=False)
        cur.execute("SELECT version, sha256, size_bytes, mime, scan_status, created_by, created_at FROM aav.vfs_versions "
                    "WHERE node_id = %s ORDER BY version DESC", (node_id,))
        return cur.fetchall()


@router.post("/{node_id}/verify")
def verify_checksum(node_id: UUID, p: Principal = Depends(need("files.read"))):
    import hashlib
    with db.tenant_tx(p.tenant_id) as cur:
        n = _get_node(cur, node_id)
        cur.execute("SELECT sha256, storage_key FROM aav.vfs_versions WHERE node_id = %s AND version = %s",
                    (node_id, n["current_version"]))
        v = cur.fetchone()
    h = hashlib.sha256()
    with open(_blob_path(p.tenant_id, v["storage_key"]), "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return {"expected": v["sha256"], "actual": h.hexdigest(), "ok": h.hexdigest() == v["sha256"]}


def _walk(cur, node_id, prefix: str):
    n = _get_node(cur, node_id)
    path = f"{prefix}{n['name']}"
    if n["kind"] == "file":
        cur.execute("SELECT storage_key FROM aav.vfs_versions WHERE node_id = %s AND version = %s",
                    (node_id, n["current_version"]))
        yield path, cur.fetchone()["storage_key"]
    else:
        cur.execute("SELECT id FROM aav.vfs_nodes WHERE parent_id = %s AND trashed_at IS NULL ORDER BY name", (node_id,))
        for c in cur.fetchall():
            yield from _walk(cur, c["id"], path + "/")


@router.get("/{node_id}/export")
def export(node_id: UUID, fmt: str = "zip", p: Principal = Depends(need("files.read"))):
    if fmt not in ("zip", "tar", "tar.gz"):
        raise HTTPException(422, "fmt must be zip, tar or tar.gz")
    with db.tenant_tx(p.tenant_id) as cur:
        entries = list(_walk(cur, node_id, ""))
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="file.export", target=str(node_id),
                     detail={"fmt": fmt, "files": len(entries)})
    spool = tempfile.SpooledTemporaryFile(max_size=32 * 1024 * 1024)
    if fmt == "zip":
        with zipfile.ZipFile(spool, "w", zipfile.ZIP_DEFLATED) as z:
            for path, key in entries:
                z.write(_blob_path(p.tenant_id, key), path)
    else:
        with tarfile.open(fileobj=spool, mode="w:gz" if fmt == "tar.gz" else "w") as t:
            for path, key in entries:
                t.add(_blob_path(p.tenant_id, key), path, recursive=False)
    spool.seek(0)
    return StreamingResponse(iter(lambda: spool.read(1 << 20), b""), media_type="application/octet-stream",
                             headers={"Content-Disposition": f'attachment; filename="export.{fmt}"'})


MAX_ARCHIVE_ENTRIES = 10000


def _safe_parts(name: str) -> list[str]:
    p = PurePosixPath(name.replace("\\", "/"))
    if not p.parts or p.is_absolute() or any(part in ("..", "") for part in p.parts) or ":" in p.parts[0]:
        raise HTTPException(422, f"unsafe path in archive: {name!r}")
    return [_check_name(part) for part in p.parts]


@router.post("/import", status_code=201)
async def bulk_import(file: UploadFile, parent_id: UUID | None = None, p: Principal = Depends(need("files.write"))):
    """Import a zip / tar / tar.gz recursively. Rejects absolute paths, '..', symlinks, hard
    links, devices, and archives over the entry limit; every file is scanned like an upload."""
    data = file.file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, "archive too large")
    members: list[tuple[list[str], bytes]] = []
    if data[:4] == b"PK\x03\x04":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos = z.infolist()
            if len(infos) > MAX_ARCHIVE_ENTRIES:
                raise HTTPException(422, "too many entries")
            for i in infos:
                if (i.external_attr >> 16) & 0o170000 == 0o120000:
                    raise HTTPException(422, f"symlink in archive: {i.filename!r}")
                parts = _safe_parts(i.filename.rstrip("/"))
                if not i.is_dir():
                    members.append((parts, z.read(i)))
    else:
        try:
            t = tarfile.open(fileobj=io.BytesIO(data), mode="r:*")
        except tarfile.TarError:
            raise HTTPException(422, "not a zip or tar archive")
        with t:
            infos = t.getmembers()
            if len(infos) > MAX_ARCHIVE_ENTRIES:
                raise HTTPException(422, "too many entries")
            for m in infos:
                if m.issym() or m.islnk() or m.isdev() or m.isfifo():
                    raise HTTPException(422, f"link or special file in archive: {m.name!r}")
                parts = _safe_parts(m.name.rstrip("/"))
                if m.isfile():
                    members.append((parts, t.extractfile(m).read()))
    created = 0
    with db.tenant_tx(p.tenant_id) as cur:
        _ensure_dir(cur, parent_id)
        used = _usage(cur)
    for parts, content in members:
        blob = _store_stream(p.tenant_id, [content], parts[-1])
        with db.tenant_tx(p.tenant_id) as cur:
            if blob["scan_status"] != "clean":
                audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="file.import_rejected",
                             target="/".join(parts), detail={"scan": blob["scan"]})
                cur.connection.commit()
                raise HTTPException(422, {"error": "archive member rejected", "path": "/".join(parts),
                                          "scan": blob["scan"]})
            used += blob["size"]
            if used > settings.tenant_quota_bytes:
                raise HTTPException(507, "tenant storage quota exceeded")
            cur_parent = parent_id
            for d in parts[:-1]:
                cur.execute("SELECT id, kind FROM aav.vfs_nodes WHERE parent_id IS NOT DISTINCT FROM %s AND name = %s "
                            "AND trashed_at IS NULL", (cur_parent, d))
                r = cur.fetchone()
                if r and r["kind"] != "dir":
                    raise HTTPException(409, f"{d} is a file")
                if not r:
                    cur.execute("INSERT INTO aav.vfs_nodes (tenant_id, parent_id, name, kind, created_by) VALUES "
                                "(%s,%s,%s,'dir',%s) RETURNING id", (p.tenant_id, cur_parent, d, p.user_id))
                    r = cur.fetchone()
                cur_parent = r["id"]
            cur.execute("SELECT id FROM aav.vfs_nodes WHERE parent_id IS NOT DISTINCT FROM %s AND name = %s AND "
                        "trashed_at IS NULL AND kind = 'file'", (cur_parent, parts[-1]))
            r = cur.fetchone()
            if not r:
                cur.execute("INSERT INTO aav.vfs_nodes (tenant_id, parent_id, name, kind, created_by) VALUES "
                            "(%s,%s,%s,'file',%s) RETURNING id", (p.tenant_id, cur_parent, parts[-1], p.user_id))
                r = cur.fetchone()
            _add_version(cur, p, r["id"], blob)
            created += 1
    with db.tenant_tx(p.tenant_id) as cur:
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="file.import", target=str(parent_id),
                     detail={"files": created})
    return {"imported": created}

