"""Media Studio API: agentic music, voice, image, video and script generation, the film pipeline
(storyboard → shots → timeline → EDL), media-app templates and governed social publishing.

Governance (same principles as agent runs and tool calls):
  * Editors propose; owners/admins approve. With IDE_MEDIA_FOUR_EYES=true the approver must differ from the requester.
  * An approval is bound to the SHA-256 digest of the exact content. Editing a post resets it to draft.
  * Every transition is a single conditional UPDATE, so double-clicks and races cannot double-spend or double-post.
  * Providers and platforms are off until enabled by environment; "mock" gives free, deterministic output.
  * Every action is written to the append-only ide_media_audit table.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import DateTime, Integer, LargeBinary, String, Text, Uuid, func, select, text, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from . import media_providers as mp
from . import media_templates
from . import social
from .main import Base, Principal, WorkspaceFile, db_session, principal, project_or_404, safe_path

router = APIRouter()
EDITORS = ("owner", "admin", "editor")
APPROVERS = ("owner", "admin")
STORYBOARD_PATH = "media/storyboard.json"
MAX_DATA_URI_BYTES = 5 * 1024 * 1024


# ---------- persistence ----------

class MediaJob(Base):
    __tablename__ = "ide_media_jobs"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128))
    project_id: Mapped[str] = mapped_column(String(36))
    requested_by: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(16))
    provider: Mapped[str] = mapped_column(String(32))
    prompt: Mapped[str] = mapped_column(Text)
    params: Mapped[dict] = mapped_column(JSONB, default=dict)
    digest: Mapped[str] = mapped_column(String(64))
    estimate_pence: Mapped[int] = mapped_column(Integer, default=0)
    state: Mapped[str] = mapped_column(String(16), default="proposed")
    approved_by: Mapped[str | None] = mapped_column(String(255))
    approved_digest: Mapped[str | None] = mapped_column(String(64))
    external_id: Mapped[str | None] = mapped_column(String(255))
    result_url: Mapped[str | None] = mapped_column(Text)
    result_text: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MediaAsset(Base):
    __tablename__ = "ide_media_assets"
    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    job_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    content_type: Mapped[str] = mapped_column(String(64))
    sha256: Mapped[str] = mapped_column(String(64))
    data: Mapped[bytes] = mapped_column(LargeBinary)


class SocialPost(Base):
    __tablename__ = "ide_social_posts"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128))
    project_id: Mapped[str] = mapped_column(String(36))
    created_by: Mapped[str] = mapped_column(String(255))
    platform: Mapped[str] = mapped_column(String(16))
    body: Mapped[str] = mapped_column(Text)
    media_job_ids: Mapped[list] = mapped_column(JSONB, default=list)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    digest: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16), default="draft")
    approved_by: Mapped[str | None] = mapped_column(String(255))
    approved_digest: Mapped[str | None] = mapped_column(String(64))
    external_id: Mapped[str | None] = mapped_column(String(255))
    external_url: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MediaAudit(Base):
    __tablename__ = "ide_media_audit"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128))
    object_type: Mapped[str] = mapped_column(String(16))
    object_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    actor: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(32))
    digest: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


def digest_of(obj: dict) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _audit(db: Session, p: Principal, kind: str, object_id: str, action: str, digest: str | None = None) -> None:
    db.add(MediaAudit(id=str(uuid.uuid4()), tenant_id=p.tenant_id, object_type=kind, object_id=object_id,
                      actor=p.subject, action=action, digest=digest))


def _commit(db: Session, p: Principal) -> None:
    """Commit, then re-apply the tenant scope. db_session sets ide.tenant_id with SET LOCAL, which ends with
    the transaction; without this, every query after an intermediate commit would see zero rows under RLS."""
    db.commit()
    db.execute(text("SELECT set_config('ide.tenant_id', :tenant, true)"), {"tenant": p.tenant_id})


def _require(p: Principal, roles: tuple[str, ...], message: str) -> None:
    if p.role not in roles:
        raise HTTPException(403, message)


def _uuid(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(404, "Not found") from None


def _four_eyes(p: Principal, requester: str) -> None:
    if os.getenv("IDE_MEDIA_FOUR_EYES") == "true" and p.subject == requester:
        raise HTTPException(403, "Four-eyes policy: someone else must approve")


# ---------- API models ----------

class MediaJobIn(BaseModel):
    kind: Literal["image", "video", "music", "voice", "script"]
    provider: str = Field(min_length=1, max_length=32)
    prompt: str = Field(min_length=1, max_length=4000)
    params: dict = Field(default_factory=dict)


class SocialPostIn(BaseModel):
    platform: Literal["mock", "mastodon", "x", "linkedin", "youtube", "tiktok", "instagram"]
    body: str = Field(min_length=1, max_length=5000)
    media_job_ids: list[str] = Field(default_factory=list, max_length=4)
    scheduled_for: datetime | None = None

    @field_validator("scheduled_for")
    @classmethod
    def aware(cls, v):
        if v is not None and v.tzinfo is None:
            raise ValueError("scheduled_for needs a timezone")
        return v


class SocialPostEdit(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    scheduled_for: datetime | None = None


SLUG = r"^[a-z0-9][a-z0-9-]{0,39}$"


class Shot(BaseModel):
    id: str = Field(pattern=SLUG)
    description: str = Field(max_length=1000)
    duration_s: float = Field(gt=0, le=600)
    media_job_id: str | None = None


class Scene(BaseModel):
    id: str = Field(pattern=SLUG)
    title: str = Field(max_length=200)
    script: str = Field(default="", max_length=20000)
    shots: list[Shot] = Field(default_factory=list, max_length=100)


class Clip(BaseModel):
    shot_id: str = Field(pattern=SLUG)
    start_s: float = Field(ge=0)
    end_s: float = Field(gt=0)


class Storyboard(BaseModel):
    title: str = Field(max_length=200)
    logline: str = Field(default="", max_length=1000)
    fps: Literal[24, 25, 30] = 25
    soundtrack_job_id: str | None = None
    scenes: list[Scene] = Field(default_factory=list, max_length=200)
    timeline: list[Clip] = Field(default_factory=list, max_length=2000)

    @model_validator(mode="after")
    def consistent(self):
        shot_ids = [s.id for sc in self.scenes for s in sc.shots]
        if len(shot_ids) != len(set(shot_ids)):
            raise ValueError("shot ids must be unique")
        if len({sc.id for sc in self.scenes}) != len(self.scenes):
            raise ValueError("scene ids must be unique")
        known, last_end = set(shot_ids), 0.0
        for clip in sorted(self.timeline, key=lambda c: c.start_s):
            if clip.shot_id not in known:
                raise ValueError(f"timeline references unknown shot {clip.shot_id}")
            if clip.end_s <= clip.start_s:
                raise ValueError("clip end must be after start")
            if clip.start_s < last_end - 1e-6:
                raise ValueError("timeline clips overlap")
            last_end = clip.end_s
        return self


# ---------- helpers ----------

def job_out(job: MediaJob, has_asset: bool = False) -> dict:
    return {"id": job.id, "project_id": job.project_id, "kind": job.kind, "provider": job.provider,
            "prompt": job.prompt, "params": job.params, "estimate_pence": job.estimate_pence, "state": job.state,
            "requested_by": job.requested_by, "approved_by": job.approved_by, "digest": job.digest,
            "result_url": job.result_url, "result_text": job.result_text, "error": job.error,
            "has_asset": has_asset, "created_at": job.created_at}


def post_out(post: SocialPost) -> dict:
    platform = social.PLATFORMS[post.platform]
    return {"id": post.id, "project_id": post.project_id, "platform": post.platform, "mode": platform.mode,
            "body": post.body, "media_job_ids": post.media_job_ids, "scheduled_for": post.scheduled_for,
            "state": post.state, "created_by": post.created_by, "approved_by": post.approved_by,
            "digest": post.digest, "external_id": post.external_id, "external_url": post.external_url,
            "error": post.error, "created_at": post.created_at}


def _job(db: Session, p: Principal, job_id: str) -> MediaJob:
    job = db.scalar(select(MediaJob).where(MediaJob.id == _uuid(job_id), MediaJob.tenant_id == p.tenant_id))
    if job is None:
        raise HTTPException(404, "Media job not found")
    return job


def _post(db: Session, p: Principal, post_id: str) -> SocialPost:
    post = db.scalar(select(SocialPost).where(SocialPost.id == _uuid(post_id), SocialPost.tenant_id == p.tenant_id))
    if post is None:
        raise HTTPException(404, "Post not found")
    return post


def _has_asset(db: Session, p: Principal, job_id: str) -> bool:
    return db.scalar(select(func.count()).select_from(MediaAsset).where(
        MediaAsset.tenant_id == p.tenant_id, MediaAsset.job_id == job_id)) > 0


def _succeeded_job(db: Session, p: Principal, project_id: str, job_id: str, kind: str | None = None) -> MediaJob:
    job = db.scalar(select(MediaJob).where(MediaJob.id == _uuid(job_id), MediaJob.tenant_id == p.tenant_id,
                                           MediaJob.project_id == project_id))
    if job is None or job.state != "succeeded" or (kind and job.kind != kind):
        raise HTTPException(422, f"Media job {job_id} is not a finished {kind or 'media'} job in this project")
    return job


def _post_digest(platform: str, body: str, media: list[str], scheduled: datetime | None) -> str:
    return digest_of({"platform": platform, "body": body, "media": media,
                      "scheduled_for": scheduled.astimezone(timezone.utc).isoformat() if scheduled else None})


# ---------- capabilities and templates ----------

@router.get("/api/v1/media/capabilities")
def media_capabilities(p: Principal = Depends(principal)):
    return {"providers": mp.capabilities(), "platforms": social.capabilities(), "templates": media_templates.listing(),
            "approval_required": True, "four_eyes": os.getenv("IDE_MEDIA_FOUR_EYES") == "true"}


@router.post("/api/v1/projects/{project_id}/media-templates/{template_id}", status_code=201)
def apply_template(project_id: str, template_id: str, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    _require(p, EDITORS, "Read-only membership")
    project_or_404(db, p.tenant_id, project_id)
    template = media_templates.TEMPLATES.get(template_id)
    if template is None:
        raise HTTPException(404, "Template not found")
    created, skipped = [], []
    for path, content in template["files"].items():
        path = safe_path(path)
        if db.get(WorkspaceFile, (p.tenant_id, project_id, path)) is not None:
            skipped.append(path)  # never overwrite the user's work
            continue
        db.add(WorkspaceFile(tenant_id=p.tenant_id, project_id=project_id, path=path, content=content))
        created.append(path)
    _commit(db, p)
    return {"template": template_id, "created": created, "skipped": skipped}


# ---------- film pipeline ----------

def _load_storyboard(db: Session, p: Principal, project_id: str) -> Storyboard:
    project_or_404(db, p.tenant_id, project_id)
    file = db.get(WorkspaceFile, (p.tenant_id, project_id, STORYBOARD_PATH))
    if file is None:
        return Storyboard(title="Untitled")
    try:
        return Storyboard.model_validate_json(file.content)
    except ValueError:
        raise HTTPException(422, f"{STORYBOARD_PATH} is not a valid storyboard") from None


@router.get("/api/v1/projects/{project_id}/storyboard")
def get_storyboard(project_id: str, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    return _load_storyboard(db, p, project_id).model_dump()


@router.put("/api/v1/projects/{project_id}/storyboard")
def save_storyboard(project_id: str, body: Storyboard, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    _require(p, EDITORS, "Read-only membership")
    project_or_404(db, p.tenant_id, project_id)
    content = json.dumps(body.model_dump(), indent=2) + "\n"
    file = db.get(WorkspaceFile, (p.tenant_id, project_id, STORYBOARD_PATH))
    if file is None:
        db.add(WorkspaceFile(tenant_id=p.tenant_id, project_id=project_id, path=STORYBOARD_PATH, content=content))
    else:
        file.content = content
    _commit(db, p)
    return body.model_dump()


def timecode(seconds: float, fps: int) -> str:
    frames = int(round(seconds * fps))
    h, rem = divmod(frames, 3600 * fps)
    m, rem = divmod(rem, 60 * fps)
    s, f = divmod(rem, fps)
    return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"


def export_edl(board: Storyboard) -> str:
    """CMX3600 edit decision list: one video event per timeline clip (opens in Resolve, Premiere, Avid)."""
    title = re.sub(r"[^A-Za-z0-9 _-]", "", board.title)[:60] or "AEPX"
    lines = [f"TITLE: {title}", "FCM: NON-DROP FRAME", ""]
    for n, clip in enumerate(sorted(board.timeline, key=lambda c: c.start_s), start=1):
        length = clip.end_s - clip.start_s
        reel = clip.shot_id.replace("-", "")[:8].upper() or "AX"
        lines.append(f"{n:03d}  {reel:<8} V     C        {timecode(0, board.fps)} {timecode(length, board.fps)} "
                     f"{timecode(clip.start_s, board.fps)} {timecode(clip.end_s, board.fps)}")
        lines.append(f"* FROM CLIP NAME: {clip.shot_id}.mp4")
        lines.append("")
    return "\n".join(lines)


def export_ffmpeg(board: Storyboard) -> str:
    """POSIX shell script: trims each shot clip to its timeline length and concatenates them.
    Shot ids are validated slugs ([a-z0-9-]), so they are safe inside single quotes."""
    out = ["#!/bin/sh", "# Generated by AEP-X Media Studio. Put each shot as <shot-id>.mp4 next to this script.",
           "set -eu", ": > list.txt"]
    for n, clip in enumerate(sorted(board.timeline, key=lambda c: c.start_s)):
        length = round(clip.end_s - clip.start_s, 3)
        out.append(f"ffmpeg -y -i '{clip.shot_id}.mp4' -t {length} -c:v libx264 -c:a aac 'part-{n:03d}.mp4'")
        out.append(f"echo \"file 'part-{n:03d}.mp4'\" >> list.txt")
    out.append("ffmpeg -y -f concat -safe 0 -i list.txt -c copy film.mp4")
    return "\n".join(out) + "\n"


@router.get("/api/v1/projects/{project_id}/storyboard/export")
def storyboard_export(project_id: str, format: Literal["edl", "ffmpeg"] = "edl",
                      p: Principal = Depends(principal), db: Session = Depends(db_session)):
    board = _load_storyboard(db, p, project_id)
    text_out = export_edl(board) if format == "edl" else export_ffmpeg(board)
    name = "film.edl" if format == "edl" else "render.sh"
    return PlainTextResponse(text_out, headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ---------- media jobs ----------

@router.post("/api/v1/projects/{project_id}/media-jobs", status_code=201)
def create_media_job(project_id: str, body: MediaJobIn, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    _require(p, EDITORS, "Read-only membership")
    project_or_404(db, p.tenant_id, project_id)
    try:
        provider = mp.get(body.provider)
    except ValueError:
        raise HTTPException(400, "Unknown provider") from None
    if body.kind not in provider.kinds:
        raise HTTPException(400, f"{provider.name} does not generate {body.kind}")
    if not provider.configured():
        raise HTTPException(409, f"{provider.name} is not enabled on this deployment")
    try:
        params = provider.validate(body.kind, body.params)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    if params.get("image_job_id"):
        params["image_job_id"] = _succeeded_job(db, p, project_id, params["image_job_id"], "image").id
    estimate = provider.estimate_pence(body.kind, body.prompt, params)
    digest = digest_of({"kind": body.kind, "provider": provider.name, "prompt": body.prompt, "params": params})
    job = MediaJob(id=str(uuid.uuid4()), tenant_id=p.tenant_id, project_id=project_id, requested_by=p.subject,
                   kind=body.kind, provider=provider.name, prompt=body.prompt, params=params, digest=digest,
                   estimate_pence=estimate, state="proposed")
    db.add(job)
    db.flush()
    _audit(db, p, "media_job", job.id, "proposed", digest)
    _commit(db, p)
    return job_out(job)


@router.get("/api/v1/projects/{project_id}/media-jobs")
def list_media_jobs(project_id: str, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    project_or_404(db, p.tenant_id, project_id)
    jobs = db.scalars(select(MediaJob).where(MediaJob.tenant_id == p.tenant_id, MediaJob.project_id == project_id)
                      .order_by(MediaJob.created_at.desc()).limit(200)).all()
    with_assets = set(db.scalars(select(MediaAsset.job_id).where(
        MediaAsset.tenant_id == p.tenant_id, MediaAsset.job_id.in_([j.id for j in jobs])))) if jobs else set()
    return [job_out(j, j.id in with_assets) for j in jobs]


@router.get("/api/v1/media-jobs/{job_id}")
def media_job_detail(job_id: str, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    job = _job(db, p, job_id)
    return job_out(job, _has_asset(db, p, job.id))


@router.post("/api/v1/media-jobs/{job_id}/decision")
def decide_media_job(job_id: str, approved: bool, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    _require(p, APPROVERS, "Only owners/admins can approve media generation")
    job = _job(db, p, job_id)
    _four_eyes(p, job.requested_by)
    values = ({"state": "approved", "approved_by": p.subject, "approved_digest": job.digest} if approved
              else {"state": "rejected"})
    changed = db.execute(update(MediaJob).where(
        MediaJob.id == job.id, MediaJob.tenant_id == p.tenant_id, MediaJob.state == "proposed",
        MediaJob.digest == job.digest).values(**values, updated_at=func.now()).returning(MediaJob.id)).first()
    if changed is None:
        raise HTTPException(409, "Job was already decided")
    _audit(db, p, "media_job", job.id, "approved" if approved else "rejected", job.digest)
    _commit(db, p)
    db.refresh(job)
    return job_out(job)


def _apply_result(db: Session, p: Principal, job: MediaJob, result: mp.Result) -> None:
    job.state = result.state
    job.external_id = result.external_id or job.external_id
    job.result_url = result.result_url or job.result_url
    job.result_text = result.result_text or job.result_text
    job.error = result.error
    job.updated_at = datetime.now(timezone.utc)
    if result.asset:
        if len(result.asset) > mp.MAX_ASSET_BYTES:
            job.state, job.error = "failed", "Generated file exceeds 20 MB"
        else:
            db.merge(MediaAsset(tenant_id=p.tenant_id, job_id=job.id,
                                content_type=result.content_type or "application/octet-stream",
                                sha256=hashlib.sha256(result.asset).hexdigest(), data=result.asset))
    _audit(db, p, "media_job", job.id, job.state, job.digest)


def _guarded(call) -> mp.Result:
    try:
        return call()
    except mp.MediaProviderError as exc:
        return mp.Result("failed", error=str(exc)[:300])
    except httpx.HTTPError:
        return mp.Result("failed", error="Provider could not be reached")
    except (KeyError, ValueError, TypeError, IndexError):
        return mp.Result("failed", error="Provider returned an unexpected response")


@router.post("/api/v1/media-jobs/{job_id}/run")
def run_media_job(job_id: str, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    _require(p, EDITORS, "Read-only membership")
    job = _job(db, p, job_id)
    provider = mp.get(job.provider)
    if not provider.configured():
        raise HTTPException(409, f"{provider.name} is not enabled on this deployment")
    claimed = db.execute(update(MediaJob).where(
        MediaJob.id == job.id, MediaJob.tenant_id == p.tenant_id, MediaJob.state == "approved",
        MediaJob.approved_digest == MediaJob.digest).values(state="running", updated_at=func.now())
        .returning(MediaJob.id)).first()
    if claimed is None:
        raise HTTPException(409, "Job must be approved (and not already started) before it runs")
    _audit(db, p, "media_job", job.id, "started", job.digest)
    _commit(db, p)  # the claim is durable before any paid call is made

    params = dict(job.params)
    if params.get("image_job_id"):
        source = _succeeded_job(db, p, job.project_id, params["image_job_id"], "image")
        asset = db.get(MediaAsset, (p.tenant_id, source.id))
        if asset is not None and len(asset.data) <= MAX_DATA_URI_BYTES:
            params["image_data_uri"] = f"data:{asset.content_type};base64," + base64.b64encode(asset.data).decode()
        elif source.result_url:
            params["image_url"] = source.result_url
    result = _guarded(lambda: provider.submit(job.kind, job.prompt, params))
    db.refresh(job)
    _apply_result(db, p, job, result)
    _commit(db, p)
    return job_out(job, _has_asset(db, p, job.id))


@router.post("/api/v1/media-jobs/{job_id}/refresh")
def refresh_media_job(job_id: str, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    job = _job(db, p, job_id)
    if job.state != "running" or not job.external_id:
        return job_out(job, _has_asset(db, p, job.id))
    result = _guarded(lambda: mp.get(job.provider).poll(job.external_id))
    if result.state != "running":
        _apply_result(db, p, job, result)
        _commit(db, p)
    return job_out(job, _has_asset(db, p, job.id))


@router.get("/api/v1/media-jobs/{job_id}/asset")
def media_asset(job_id: str, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    job = _job(db, p, job_id)
    asset = db.get(MediaAsset, (p.tenant_id, job.id))
    if asset is None:
        raise HTTPException(404, "No file for this job")
    ext = {"image/png": "png", "image/svg+xml": "svg", "audio/mpeg": "mp3", "audio/wav": "wav"}.get(asset.content_type, "bin")
    return Response(asset.data, media_type=asset.content_type, headers={
        # Generated content is untrusted: never let it run script or load anything in the IDE origin.
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
        "X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=300",
        "Content-Disposition": f'inline; filename="{job.kind}-{job.id[:8]}.{ext}"', "ETag": f'"{asset.sha256}"'})


@router.get("/api/v1/media-audit/{object_id}")
def media_audit(object_id: str, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    rows = db.scalars(select(MediaAudit).where(MediaAudit.tenant_id == p.tenant_id, MediaAudit.object_id == _uuid(object_id))
                      .order_by(MediaAudit.created_at)).all()
    return [{"actor": r.actor, "action": r.action, "digest": r.digest, "at": r.created_at} for r in rows]


# ---------- social posts ----------

@router.post("/api/v1/projects/{project_id}/social-posts", status_code=201)
def create_social_post(project_id: str, body: SocialPostIn, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    _require(p, EDITORS, "Read-only membership")
    project_or_404(db, p.tenant_id, project_id)
    platform = social.get(body.platform)
    try:
        platform.validate(body.body)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    media = [_succeeded_job(db, p, project_id, j).id for j in body.media_job_ids]
    post = SocialPost(id=str(uuid.uuid4()), tenant_id=p.tenant_id, project_id=project_id, created_by=p.subject,
                      platform=body.platform, body=body.body, media_job_ids=media, scheduled_for=body.scheduled_for,
                      digest=_post_digest(body.platform, body.body, media, body.scheduled_for), state="draft")
    db.add(post)
    db.flush()
    _audit(db, p, "social_post", post.id, "drafted", post.digest)
    _commit(db, p)
    return post_out(post)


@router.get("/api/v1/projects/{project_id}/social-posts")
def list_social_posts(project_id: str, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    project_or_404(db, p.tenant_id, project_id)
    posts = db.scalars(select(SocialPost).where(SocialPost.tenant_id == p.tenant_id, SocialPost.project_id == project_id)
                       .order_by(SocialPost.created_at.desc()).limit(200)).all()
    return [post_out(x) for x in posts]


@router.put("/api/v1/social-posts/{post_id}")
def edit_social_post(post_id: str, body: SocialPostEdit, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    _require(p, EDITORS, "Read-only membership")
    post = _post(db, p, post_id)
    try:
        social.get(post.platform).validate(body.body)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    if body.scheduled_for is not None and body.scheduled_for.tzinfo is None:
        raise HTTPException(422, "scheduled_for needs a timezone")
    new_digest = _post_digest(post.platform, body.body, post.media_job_ids, body.scheduled_for)
    # Any edit voids an earlier approval: the approver must see the final text.
    changed = db.execute(update(SocialPost).where(
        SocialPost.id == post.id, SocialPost.tenant_id == p.tenant_id,
        SocialPost.state.in_(("draft", "approved", "rejected", "failed"))).values(
        body=body.body, scheduled_for=body.scheduled_for, digest=new_digest, state="draft",
        approved_by=None, approved_digest=None, error=None, updated_at=func.now()).returning(SocialPost.id)).first()
    if changed is None:
        raise HTTPException(409, "Published posts cannot be edited")
    _audit(db, p, "social_post", post.id, "edited", new_digest)
    _commit(db, p)
    db.refresh(post)
    return post_out(post)


@router.post("/api/v1/social-posts/{post_id}/decision")
def decide_social_post(post_id: str, approved: bool, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    _require(p, APPROVERS, "Only owners/admins can approve public posts")
    post = _post(db, p, post_id)
    _four_eyes(p, post.created_by)
    values = ({"state": "approved", "approved_by": p.subject, "approved_digest": post.digest} if approved
              else {"state": "rejected"})
    changed = db.execute(update(SocialPost).where(
        SocialPost.id == post.id, SocialPost.tenant_id == p.tenant_id, SocialPost.state == "draft",
        SocialPost.digest == post.digest).values(**values, updated_at=func.now()).returning(SocialPost.id)).first()
    if changed is None:
        raise HTTPException(409, "Post changed or was already decided")
    _audit(db, p, "social_post", post.id, "approved" if approved else "rejected", post.digest)
    _commit(db, p)
    db.refresh(post)
    return post_out(post)


def _publish(db: Session, p: Principal, post: SocialPost) -> SocialPost:
    platform = social.get(post.platform)
    if not platform.configured():
        raise HTTPException(409, f"{post.platform} is not enabled on this deployment")
    now = datetime.now(timezone.utc)
    claimed = db.execute(update(SocialPost).where(
        SocialPost.id == post.id, SocialPost.tenant_id == p.tenant_id, SocialPost.state == "approved",
        SocialPost.approved_digest == SocialPost.digest,
        (SocialPost.scheduled_for.is_(None)) | (SocialPost.scheduled_for <= now)).values(
        state="publishing", updated_at=func.now()).returning(SocialPost.id)).first()
    if claimed is None:
        raise HTTPException(409, "Post must be approved, unchanged and due before it is published")
    _audit(db, p, "social_post", post.id, "publishing", post.digest)
    _commit(db, p)  # durable claim: a crash cannot lead to a second publish
    links = []
    for job_id in post.media_job_ids:
        job = db.scalar(select(MediaJob).where(MediaJob.id == job_id, MediaJob.tenant_id == p.tenant_id))
        if job is not None and job.result_url:
            links.append(job.result_url)
    db.refresh(post)
    try:
        out = platform.publish(post.id, post.body, links)
        post.state, post.external_id, post.external_url, post.error = out.state, out.external_id, out.external_url, None
    except social.SocialError as exc:
        post.state, post.error = "failed", str(exc)[:300]
    except httpx.HTTPError:
        post.state, post.error = "failed", "Platform could not be reached"
    except (KeyError, ValueError, TypeError):
        post.state, post.error = "failed", "Platform returned an unexpected response"
    post.updated_at = datetime.now(timezone.utc)
    _audit(db, p, "social_post", post.id, post.state, post.digest)
    _commit(db, p)
    return post


@router.post("/api/v1/social-posts/{post_id}/publish")
def publish_social_post(post_id: str, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    _require(p, EDITORS, "Read-only membership")
    return post_out(_publish(db, p, _post(db, p, post_id)))


@router.get("/api/v1/social-posts/{post_id}/package")
def social_post_package(post_id: str, p: Principal = Depends(principal), db: Session = Depends(db_session)):
    """Upload package for export-mode platforms (YouTube, TikTok, Instagram) once the post is approved."""
    post = _post(db, p, post_id)
    if post.state not in ("approved", "exported"):
        raise HTTPException(409, "Post must be approved first")
    media = [{"job_id": j, "asset_path": f"/api/v1/media-jobs/{j}/asset"} for j in post.media_job_ids]
    return {"platform": post.platform, "caption": post.body, "media": media, "digest": post.digest}


@router.post("/api/v1/social-posts/publish-due")
def publish_due(p: Principal = Depends(principal), db: Session = Depends(db_session)):
    """For a scheduler (cron) running as an owner/admin: publishes approved posts whose time has come."""
    _require(p, APPROVERS, "Only owners/admins can run the publisher")
    now = datetime.now(timezone.utc)
    due = db.scalars(select(SocialPost).where(
        SocialPost.tenant_id == p.tenant_id, SocialPost.state == "approved",
        SocialPost.scheduled_for.is_not(None), SocialPost.scheduled_for <= now).limit(20)).all()
    results = []
    for post in due:
        if not social.get(post.platform).configured():
            results.append({"id": post.id, "state": "skipped", "reason": "platform not enabled"})
            continue
        try:
            results.append({"id": post.id, "state": _publish(db, p, post).state})
        except HTTPException as exc:
            results.append({"id": post.id, "state": "skipped", "reason": exc.detail})
    return {"processed": results}
