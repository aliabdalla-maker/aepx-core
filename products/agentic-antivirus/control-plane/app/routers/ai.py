"""Agents across the product (PRD §3 "Agent roles and playbooks").

Playbooks (versioned in PLAYBOOKS): each role has a job, approved data sources, permitted tools, a
budget and limits. Every agent uses the LLM provider chain (llm.py) and has a deterministic fallback,
so scanning, detection, alerting and manual response never depend on a model.

  triage        incident -> summary, suggested severity, evidence-backed key points       (read-only)
  remediation   incident -> ordered plan of catalogue actions, each filed as a *proposal* (approval gate)
  assistant     question -> answer from tenant posture, open incidents, gaps and help    (read-only)
  translator    UI catalogue keys -> machine translations, labelled until reviewed      (platform admin)

Kill switch: settings llm_providers.enabled = false for a tenant turns every model call off (rules only).
"""
from __future__ import annotations

import hashlib
import json
from uuid import UUID

import base64
import unicodedata

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app import audit, db, i18n, llm
from app.catalogue import CATALOGUE
from app.deps import Principal, need
from app.routers.actions import ProposeIn, propose
from app.routers.incidents import timeline_rows
from app.routers.investigation import AI_ROLES, _sanitise, rules_findings

router = APIRouter(prefix="/v1", tags=["ai"])

PLAYBOOKS = {
    "triage": {"version": "1.0.0", "actor": "ai:triage", "sources": ["incident timeline (sanitised)"],
               "tools": [], "budget_tokens": 900, "may_write": False},
    "remediation": {"version": "1.0.0", "actor": "ai:remediation", "sources": ["incident timeline (sanitised)",
                    "action catalogue"], "tools": ["actions.propose"], "budget_tokens": 1200, "may_write": "proposals only"},
    "assistant": {"version": "1.1.0", "actor": "ai:assistant", "sources": ["device posture counts", "open incidents",
                  "open security gaps", "help topics", "files, folders, images and camera captures the user attaches "
                  "(scanned first, never stored)"], "tools": ["detection engine scan"], "budget_tokens": 900,
                  "may_write": False},
    "translator": {"version": "1.0.0", "actor": "ai:translator", "sources": ["shared/i18n/en.json"], "tools": [],
                   "budget_tokens": 4000, "may_write": "aav.translations (labelled machine:llm)"},
}

HELP_TOPICS = {
    "scan": "Run a quick, full or targeted scan from Devices; progress, gaps and cancellation are on Security.",
    "quarantine": "Quarantined files cannot run. Restoring needs an administrator, a reason and a clean rescan.",
    "isolation": "Isolating a device needs approval; the management connection stays open; it expires automatically.",
    "gaps": "Security shows Protected, Degraded, Unprotected and Unknown devices and every open gap with its owner.",
    "recovery": "After an incident: contain, quarantine/remove, mitigate, rescan, then approve return to service.",
}


def _enabled(cur) -> bool:
    cur.execute("SELECT value FROM aav.settings WHERE category = 'llm_providers' AND key = 'enabled'")
    row = cur.fetchone()
    return row is None or row["value"] is not False


class AgentIn(BaseModel):
    language: str = Field(default="en", max_length=12)


class AskIn(AgentIn):
    question: str = Field(min_length=2, max_length=2000)


class TranslateIn(BaseModel):
    locale: str
    max_keys: int = Field(default=400, ge=1, le=2000)


class ReviewIn(BaseModel):
    locale: str
    keys: list[str] = Field(min_length=1, max_length=2000)


def _lang(code: str) -> str:
    return code if code in i18n.LOCALES else "en"


@router.get("/ai/status")
def ai_status(p: Principal = Depends(need("kpi.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        enabled = _enabled(cur)
        cur.execute("SELECT provider, purpose, count(*) AS calls, sum(CASE WHEN ok THEN 1 ELSE 0 END) AS ok, "
                    "sum(input_tokens) AS input_tokens, sum(output_tokens) AS output_tokens, sum(cost_usd) AS cost_usd "
                    "FROM aav.llm_usage WHERE created_at >= date_trunc('month', now()) GROUP BY provider, purpose "
                    "ORDER BY provider, purpose")
        usage = cur.fetchall()
    return {"enabled_for_tenant": enabled, **llm.status(p.tenant_id), "playbooks": PLAYBOOKS,
            "usage_this_month": [{**u, "cost_usd": float(u["cost_usd"] or 0)} for u in usage]}


def _evidence(cur, incident_id: UUID) -> list[dict]:
    cur.execute("SELECT id, title, severity, status FROM aav.incidents WHERE id = %s", (incident_id,))
    if not cur.fetchone():
        raise HTTPException(404, "incident not found")
    return [_sanitise(i) for i in timeline_rows(cur, incident_id)]


@router.post("/incidents/{incident_id}/triage")
def triage(incident_id: UUID, body: AgentIn, p: Principal = Depends(need("incidents.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        evidence = _evidence(cur, incident_id)
        enabled = _enabled(cur)
    refs = {e["ref"] for e in evidence}
    sev = max((e.get("severity") for e in evidence if e.get("severity") in ("low", "medium", "high", "critical")),
              key=["low", "medium", "high", "critical"].index, default="medium")
    out = {"engine": "rules", "summary": f"{len(evidence)} evidence items; highest severity {sev}.",
           "suggested_severity": sev, "key_points": [
               {"statement": e.get("summary") or f"{e['type']} {e.get('kind') or e.get('category') or ''}".strip(),
                "evidence_refs": [e["ref"]]} for e in evidence[:8]]}
    res = llm.complete("triage", "Summarise the incident for an on-call analyst. Return JSON {\"summary\": str "
                       "(<= 80 words), \"suggested_severity\": \"low|medium|high|critical\", \"key_points\": "
                       "[{\"statement\": str, \"evidence_refs\": [ref]}]}. Cite only refs present in the data.",
                       {"evidence": evidence}, tenant_id=p.tenant_id, language=_lang(body.language),
                       max_tokens=PLAYBOOKS["triage"]["budget_tokens"]) if enabled and evidence else None
    data = res.json() if res else None
    if isinstance(data, dict) and isinstance(data.get("summary"), str):
        points = [{"statement": str(k.get("statement", ""))[:400],
                   "evidence_refs": [r for r in k.get("evidence_refs", []) if r in refs]}
                  for k in data.get("key_points", []) if isinstance(k, dict)]
        out = {"engine": f"llm:{res.provider}:{res.model}", "summary": data["summary"][:1200],
               "suggested_severity": data.get("suggested_severity") if data.get("suggested_severity") in
               ("low", "medium", "high", "critical") else sev,
               "key_points": [k for k in points if k["evidence_refs"]],
               "unsupported_points_dropped": sum(1 for k in points if not k["evidence_refs"])}
    out["playbook"] = {"role": "triage", **PLAYBOOKS["triage"]}
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("UPDATE aav.incidents SET triaged_at = now() WHERE id = %s AND triaged_at IS NULL", (incident_id,))
        audit.record(cur, tenant_id=p.tenant_id, actor=PLAYBOOKS["triage"]["actor"], action="ai.triage",
                     target=str(incident_id), detail={"engine": out["engine"], "requested_by": p.actor})
    return out


@router.post("/incidents/{incident_id}/remediation-plan", status_code=201)
def remediation_plan(incident_id: UUID, body: AgentIn, p: Principal = Depends(need("investigations.run"))):
    actor = PLAYBOOKS["remediation"]["actor"]
    with db.tenant_tx(p.tenant_id) as cur:
        evidence = _evidence(cur, incident_id)
        enabled = _enabled(cur)
        base = rules_findings(cur, incident_id, evidence)
    steps = [{"action_type": r["action_type"], "targets": r["targets"], "params": r["params"],
              "rationale": r["rationale"], "source": "rules"} for r in base["recommendations"]]
    engine = "rules"
    catalogue = {k: {"risk": a.risk, "targets": a.target_kind, "params": sorted(a.params)}
                 for k, a in CATALOGUE.items()}
    res = llm.complete("remediation_plan", "Propose an ordered remediation plan using ONLY action types from "
                       "data.catalogue and targets that appear in data.evidence. Return JSON {\"steps\": [{\"action_type\": "
                       "str, \"targets\": [str], \"params\": {}, \"rationale\": str}], \"notes\": [str]}.",
                       {"evidence": evidence, "catalogue": catalogue}, tenant_id=p.tenant_id,
                       language=_lang(body.language), max_tokens=PLAYBOOKS["remediation"]["budget_tokens"]) \
        if enabled and evidence else None
    data = res.json() if res else None
    known_targets = {str(v) for e in evidence for v in (e.get("device"), e.get("asset"), (e.get("data") or {}).get("path"))
                     if v}
    if isinstance(data, dict) and isinstance(data.get("steps"), list):
        engine = f"llm:{res.provider}:{res.model}"
        for s in data["steps"][:10]:
            if not isinstance(s, dict) or s.get("action_type") not in CATALOGUE:
                continue
            steps.append({"action_type": s["action_type"], "targets": [str(t) for t in s.get("targets", [])][:20],
                          "params": s.get("params") if isinstance(s.get("params"), dict) else {},
                          "rationale": str(s.get("rationale", ""))[:500], "source": "llm"})
    out = []
    with db.tenant_tx(p.tenant_id) as cur:
        for s in steps:
            if s["source"] == "llm" and not set(s["targets"]) <= known_targets | _device_ids(cur, s["targets"]):
                out.append({**s, "status": "dropped: target not in evidence"})
                continue
            try:
                r = propose(cur, tenant_id=p.tenant_id, body=ProposeIn(
                    action_type=s["action_type"], targets=s["targets"], params=s["params"], reason=s["rationale"] or
                    "remediation plan", incident_id=incident_id), proposed_by=actor, proposer_roles=AI_ROLES)
                out.append({**s, "action_request_id": r["id"], "status": r["status"]})
            except HTTPException as exc:
                out.append({**s, "status": f"rejected: {exc.detail}"})
        audit.record(cur, tenant_id=p.tenant_id, actor=actor, action="ai.remediation_plan", target=str(incident_id),
                     detail={"engine": engine, "steps": len(out), "requested_by": p.actor})
    return {"engine": engine, "steps": out, "playbook": {"role": "remediation", **PLAYBOOKS["remediation"]},
            "note": "Every step is a proposal in the governed action catalogue; nothing runs without its approval."}


def _device_ids(cur, targets: list[str]) -> set[str]:
    ids = []
    for t in targets:
        try:
            ids.append(str(UUID(t)))
        except ValueError:
            pass
    if not ids:
        return set()
    cur.execute("SELECT id::text AS id FROM aav.devices WHERE id = ANY(%s::uuid[])", (ids,))
    return {r["id"] for r in cur.fetchall()}


MAX_ATTACHMENTS = 20
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 25 * 1024 * 1024
MAX_IMAGE_BYTES = 3_750_000   # provider limit for one image
TEXT_EXCERPT = 4000
_MAGIC = [(b"\x89PNG\r\n\x1a\n", "image/png"), (b"\xff\xd8\xff", "image/jpeg"), (b"GIF8", "image/gif"),
          (b"PK\x03\x04", "application/zip"), (b"%PDF", "application/pdf"), (b"MZ", "application/x-msdownload"),
          (b"\x7fELF", "application/x-elf")]


def _sniff(data: bytes) -> str:
    """Type from content, never from the name or the browser's claim."""
    for magic, kind in _MAGIC:
        if data.startswith(magic):
            return kind
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    head = data[:8192]
    if b"\x00" not in head:
        try:
            head.decode("utf-8")
            return "text/plain"
        except UnicodeDecodeError:
            pass
    return "application/octet-stream"


def _clean_name(name: str) -> str:
    name = unicodedata.normalize("NFC", name or "file").replace("\\", "/")
    parts = [x for x in name.split("/") if x not in ("", ".", "..")]
    return "/".join(parts)[-300:] or "file"


def inspect_attachments(items: list[tuple[str, bytes]]) -> tuple[list[dict], list[dict], list[dict]]:
    """Scan every attachment with the detection engine. Returns (report, text excerpts, images for the model)."""
    from app.detections import current_engine
    import hashlib
    eng = current_engine()
    report, excerpts, images = [], [], []
    for name, data in items:
        kind = _sniff(data)
        sha = hashlib.sha256(data).hexdigest()
        verdict = eng.scan_bytes(data, sha) if eng else None
        row = {"name": name, "size": len(data), "sha256": sha, "type": kind,
               "verdict": ("malicious" if verdict else "clean") if eng else "not_scanned",
               "detection": {"rule_id": verdict.rule_id, "title": verdict.title, "severity": verdict.severity}
               if verdict else None, "engine_version": eng.version if eng else None}
        report.append(row)
        if verdict:
            continue   # malicious content never reaches a model; only its metadata does
        if kind == "text/plain":
            excerpts.append({"name": name, "excerpt": llm.redact(data[:TEXT_EXCERPT * 4].decode("utf-8", "replace")
                                                                 [:TEXT_EXCERPT])})
        elif kind in llm.IMAGE_TYPES and len(data) <= MAX_IMAGE_BYTES:
            images.append({"name": name, "media_type": kind, "data": base64.b64encode(data).decode()})
    return report, excerpts, images


def _rules_attachment_answer(report: list[dict]) -> str:
    bad = [r for r in report if r["verdict"] == "malicious"]
    unscanned = [r for r in report if r["verdict"] == "not_scanned"]
    parts = [f"Scanned {len(report)} attachment(s)."]
    if bad:
        parts.append("Malicious: " + "; ".join(f"{r['name']} ({r['detection']['title']})" for r in bad) +
                     ". Do not open these files. If they came from one of your devices, run a full scan of that device "
                     "from Devices; detections there are quarantined.")
    elif unscanned:
        parts.append("No detection rules are published yet, so the files could not be scanned.")
    else:
        parts.append("No known malware was found. A clean result means no rule matched; it is not a guarantee.")
    return " ".join(parts)


@router.post("/assistant/ask-with-files")
async def assistant_with_files(question: str = Form(default="", max_length=2000), language: str = Form(default="en"),
                               paths: list[str] = Form(default=[]), files: list[UploadFile] = File(default=[]),
                               p: Principal = Depends(need("kpi.read"))):
    """Ask the assistant about files, a folder, images or a camera capture. Every attachment is scanned with the
    detection engine; nothing is stored; content reaches a model only as untrusted data and malicious files never do."""
    if not files:
        raise HTTPException(422, "attach at least one file")
    if len(files) > MAX_ATTACHMENTS:
        raise HTTPException(413, f"at most {MAX_ATTACHMENTS} attachments per question")
    items, total = [], 0
    for i, f in enumerate(files):
        data = await f.read(MAX_ATTACHMENT_BYTES + 1)
        if len(data) > MAX_ATTACHMENT_BYTES:
            raise HTTPException(413, f"{f.filename}: larger than {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB")
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            raise HTTPException(413, f"attachments larger than {MAX_TOTAL_BYTES // (1024 * 1024)} MB in total")
        items.append((_clean_name(paths[i] if i < len(paths) and paths[i] else f.filename or "file"), data))
    report, excerpts, images = inspect_attachments(items)
    with db.tenant_tx(p.tenant_id) as cur:
        enabled = _enabled(cur)
    q = question.strip() or "What are these files, and are they safe?"
    out = {"engine": "rules", "answer": _rules_attachment_answer(report), "citations": []}
    res = llm.complete("assistant", "The user attached files. data.files is the engine scan report (authoritative "
                       "verdicts); data.text_excerpts are excerpts of clean text files; images are attached. Answer "
                       "data.question about them. Never contradict a scan verdict, never call a file safe beyond "
                       "'no rule matched'. Return JSON {\"answer\": str}.",
                       {"question": q, "files": report, "text_excerpts": excerpts,
                        "images": [i["name"] for i in images]},
                       tenant_id=p.tenant_id, language=_lang(language), images=images,
                       max_tokens=PLAYBOOKS["assistant"]["budget_tokens"]) if enabled else None
    data = res.json() if res else None
    images_used = 0
    if isinstance(data, dict) and isinstance(data.get("answer"), str):
        images_used = res.images_used
        out = {"engine": f"llm:{res.provider}:{res.model}", "answer": data["answer"][:3000], "citations": []}
    with db.tenant_tx(p.tenant_id) as cur:
        audit.record(cur, tenant_id=p.tenant_id, actor=PLAYBOOKS["assistant"]["actor"], action="ai.assistant.files",
                     target="", detail={"engine": out["engine"], "requested_by": p.actor, "images_to_model": images_used,
                                        "files": [{k: r[k] for k in ("name", "sha256", "size", "type", "verdict")}
                                                  for r in report]})
    return {**out, "files": report, "images_sent_to_model": images_used,
            "playbook": {"role": "assistant", **PLAYBOOKS["assistant"]}}


@router.post("/assistant/ask")
def assistant(body: AskIn, p: Principal = Depends(need("kpi.read"))):
    with db.tenant_tx(p.tenant_id) as cur:
        enabled = _enabled(cur)
        cur.execute("SELECT protection_status, count(*) AS n FROM aav.devices WHERE retired_at IS NULL "
                    "GROUP BY protection_status")
        devices = {r["protection_status"]: r["n"] for r in cur.fetchall()}
        cur.execute("SELECT id::text AS id, title, severity, status FROM aav.incidents WHERE status <> 'resolved' "
                    "ORDER BY updated_at DESC LIMIT 15")
        incidents = cur.fetchall()
        cur.execute("SELECT id::text AS id, subject_label, expected_control, severity, due_date::text AS due "
                    "FROM aav.security_gaps WHERE status = 'open' ORDER BY severity DESC, opened_at LIMIT 15")
        gaps = cur.fetchall()
    context = {"devices_by_status": devices, "open_incidents": incidents, "open_gaps": gaps, "help": HELP_TOPICS,
               "question": body.question}
    q = body.question.lower()
    fallback = [v for k, v in HELP_TOPICS.items() if k in q] or \
        [f"Devices by status: {devices or 'none enrolled'}. Open incidents: {len(incidents)}. Open gaps: {len(gaps)}."]
    out = {"engine": "rules", "answer": " ".join(fallback), "citations": []}
    res = llm.complete("assistant", "Answer the question using only data. Return JSON {\"answer\": str, "
                       "\"citations\": [id]} citing incident or gap ids you used. If data does not answer it, say so.",
                       context, tenant_id=p.tenant_id, language=_lang(body.language),
                       max_tokens=PLAYBOOKS["assistant"]["budget_tokens"]) if enabled else None
    data = res.json() if res else None
    if isinstance(data, dict) and isinstance(data.get("answer"), str):
        known = {i["id"] for i in incidents} | {g["id"] for g in gaps}
        out = {"engine": f"llm:{res.provider}:{res.model}", "answer": data["answer"][:3000],
               "citations": [c for c in data.get("citations", []) if c in known]}
    with db.tenant_tx(p.tenant_id) as cur:
        audit.record(cur, tenant_id=p.tenant_id, actor=PLAYBOOKS["assistant"]["actor"], action="ai.assistant",
                     target="", detail={"engine": out["engine"], "requested_by": p.actor})
    return {**out, "playbook": {"role": "assistant", **PLAYBOOKS["assistant"]}}


def _source_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


@router.post("/i18n/translate")
def translate(body: TranslateIn, p: Principal = Depends(need("settings.write_sensitive"))):
    """Fill missing or stale keys of one locale with the LLM chain. Results are labelled machine:llm
    until a reviewer approves them; human translations are never overwritten."""
    if body.locale not in i18n.LOCALES or body.locale == i18n.FALLBACK:
        raise HTTPException(422, "unsupported locale")
    base = i18n.base_messages()
    with db.global_tx() as cur:
        cur.execute("SELECT msg_key, source_hash, origin FROM aav.translations WHERE locale = %s", (body.locale,))
        have = {r["msg_key"]: r for r in cur.fetchall()}
    file_msgs = i18n.file_messages(body.locale)
    todo = [k for k, v in base.items()
            if k not in file_msgs and (k not in have or (have[k]["origin"] != "human" and
                                                         have[k]["source_hash"] != _source_hash(v)))][:body.max_keys]
    done, engine = 0, "none"
    for i in range(0, len(todo), 60):
        chunk = {k: base[k] for k in todo[i:i + 60]}
        res = llm.complete("translation", "Translate each value of data.messages from English for a security product "
                           "UI. Keep {placeholders}, ICU plural syntax, product names and punctuation. Return JSON with "
                           "the same keys.", {"messages": chunk}, tenant_id=None, language=body.locale,
                           max_tokens=PLAYBOOKS["translator"]["budget_tokens"])
        data = res.json() if res else None
        if not isinstance(data, dict):
            continue
        engine = f"llm:{res.provider}:{res.model}"
        with db.global_tx() as cur:
            for k, v in data.items():
                if k in chunk and isinstance(v, str) and v.strip() and i18n.placeholders(v) == i18n.placeholders(chunk[k]):
                    cur.execute("INSERT INTO aav.translations (locale, msg_key, source_hash, text, origin, provider) "
                                "VALUES (%s,%s,%s,%s,'machine:llm',%s) ON CONFLICT (locale, msg_key) DO UPDATE SET "
                                "text = EXCLUDED.text, source_hash = EXCLUDED.source_hash, provider = EXCLUDED.provider, "
                                "reviewed_by = NULL, reviewed_at = NULL, updated_at = now() "
                                "WHERE aav.translations.origin <> 'human'",
                                (body.locale, k, _source_hash(chunk[k]), v.strip(), engine))
                    done += 1
    with db.tenant_tx(p.tenant_id) as cur:
        audit.record(cur, tenant_id=p.tenant_id, actor=PLAYBOOKS["translator"]["actor"], action="i18n.translate",
                     target=body.locale, detail={"requested": len(todo), "translated": done, "engine": engine,
                                                 "requested_by": p.actor})
    return {"locale": body.locale, "missing_before": len(todo), "translated": done, "engine": engine,
            "label": "machine translated, not yet reviewed" if done else None}


@router.post("/i18n/review")
def review(body: ReviewIn, p: Principal = Depends(need("settings.write_sensitive"))):
    if body.locale not in i18n.LOCALES:
        raise HTTPException(422, "unsupported locale")
    with db.global_tx() as cur:
        cur.execute("UPDATE aav.translations SET reviewed_by = %s, reviewed_at = now(), origin = 'human' "
                    "WHERE locale = %s AND msg_key = ANY(%s) RETURNING msg_key", (p.user_id, body.locale, body.keys))
        n = len(cur.fetchall())
    with db.tenant_tx(p.tenant_id) as cur:
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="i18n.review", target=body.locale,
                     detail={"keys": n})
    return {"locale": body.locale, "reviewed": n}


def json_dumps(o) -> str:  # pragma: no cover - kept for symmetry with other routers
    return json.dumps(o, default=str)
