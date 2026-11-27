"""User-mode endpoint agent.

Trace: ARC-01, AV-01 (on-demand, quick/full/scheduled, on-download/on-access via file watching,
on-execute via new-process image scanning), AV-02, EDR-01, EDR-02, OPS-02, RSP-02, RSP-08,
THR-06 (reject unsigned updates), THR-08 (removable media, tamper), OBJ-06.

Real-time blocking (B-01, B-04): when the service runs, start_realtime() adds pre-open / pre-execute
blocking — fanotify permission events on Linux (realtime_linux.py), the AavFilter minifilter on Windows
(realtime_windows.py + kernel/windows) and the Endpoint Security extension on macOS (kernel/macos, asking
over realtime.VerdictSocketServer). Where a backend is unavailable the agent says so in its sensor health
and keeps the user-mode post-write / post-start detection below.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import psutil

from aav_detection import Engine
from aav_agent import platform_ops
from aav_agent.quarantine import Vault
from aav_agent.store import State
from aav_agent.trust import Verifier, not_expired

AGENT_VERSION = "0.1.2"
SCAN_SKIP_BYTES = 256 * 1024 * 1024
ARCHIVE_MAX_MEMBERS = 10_000
ARCHIVE_MAX_BYTES = 512 * 1024 * 1024
ARCHIVE_MAX_DEPTH = 2
PROGRESS_SECONDS = 5.0
ARCHIVE_SUFFIXES = (".zip", ".jar", ".docx", ".xlsx", ".pptx", ".apk", ".tar", ".tgz", ".tar.gz", ".tbz2", ".tar.bz2",
                    ".tar.xz", ".txz")


def _archive_kind(name: str, data: bytes | None) -> bool:
    n = name.lower()
    if data is not None:
        return data[:4] == b"PK\x03\x04" or (len(data) > 262 and data[257:262] == b"ustar")
    return n.endswith(ARCHIVE_SUFFIXES)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Agent:
    def __init__(self, state_dir: str, http: httpx.Client | None = None, base_url: str | None = None):
        self.state = State(state_dir)
        ident = self.state.get("identity")
        self.base_url = base_url or (ident or {}).get("base_url", "")
        self.http = http or httpx.Client(base_url=self.base_url, timeout=15)
        self.vault = Vault(self.state)
        self._engine: Engine | None = None
        self._known_pids: set[int] = set()
        self._file_snap: dict[str, float] = {}
        self._persist_snap: dict[str, str] | None = None
        self._mounts: set[str] | None = None
        self._fingerprint = self.state.config_fingerprint()
        self._seen_conns: set[tuple] = set()
        self._baselined = False
        self._rt = None
        self._rt_status = "not started"

    # ----------------------------------------------------------------- identity
    @property
    def identity(self) -> dict:
        ident = self.state.get("identity")
        if not ident:
            raise RuntimeError("agent not enrolled")
        return ident

    @property
    def verifier(self) -> Verifier:
        return Verifier(self.identity["control_plane_public_key"])

    def _h(self) -> dict:
        return {"X-Device-Key": self.identity["device_key"]}

    def enrol(self, token: str, hostname: str | None = None) -> dict:
        r = self.http.post("/v1/agent/enrol", json={
            "token": token, "hostname": hostname or platform.node(),
            "os": {"Windows": "windows", "Darwin": "macos"}.get(platform.system(), "linux"),
            "os_version": platform.release(), "agent_version": AGENT_VERSION})
        r.raise_for_status()
        ident = dict(r.json(), base_url=self.base_url)
        self.state.put("identity", ident)
        idf = Path(self.state.root) / "identity.json"
        idf.write_text(json.dumps({k: ident[k] for k in ("device_id", "tenant_id", "key_id")}))
        self._fingerprint = self.state.config_fingerprint()
        return ident

    # ----------------------------------------------------------------- policy
    @property
    def policy(self) -> dict:
        return (self.state.get("policy") or {}).get("bundle", {}).get("body", {})

    def refresh_policy(self) -> bool:
        """Fetch and verify. On any failure the last verified policy stays in force."""
        try:
            r = self.http.get("/v1/agent/policy", headers=self._h())
            r.raise_for_status()
            p = r.json()
        except (httpx.HTTPError, ValueError):
            return False
        b = p.get("bundle", {})
        ok = (self.verifier.ok(b, p.get("signature", "")) and b.get("device_id") == self.identity["device_id"]
              and b.get("tenant_id") == self.identity["tenant_id"])
        if not ok:
            self.emit("tamper", {"action": "invalid_policy_signature", "version": b.get("version")})
            return False
        self.state.put("policy", p)
        return True

    def excluded(self, path: str, sha256: str | None = None) -> bool:
        for e in (self.state.get("policy") or {}).get("bundle", {}).get("exclusions", []):
            if e["kind"] == "sha256" and sha256 and e["value"] == sha256:
                return True
            if e["kind"] == "path" and (path == e["value"] or fnmatch.fnmatch(path, e["value"])):
                return True
        return False

    # ----------------------------------------------------------------- updates
    def _install(self, kind: str, version: str, body: dict, signature: str) -> bool:
        if not self.verifier.ok({"kind": kind, "version": version, "body": body}, signature):
            self.emit("tamper", {"action": "invalid_update_signature", "kind": kind, "version": version})
            return False
        if kind == "detections":
            try:
                engine = Engine(body, version)
            except (ValueError, KeyError) as exc:
                self.emit("tamper", {"action": "invalid_update_content", "kind": kind, "version": version,
                                     "error": str(exc)})
                return False
            self._engine = engine
        hist = self.state.get(f"history:{kind}", [])
        if version not in [h["version"] for h in hist]:
            hist.append({"version": version, "installed_at": _now_iso()})
            (Path(self.state.root) / "updates" / f"{kind}-{version}.json").write_text(
                json.dumps({"kind": kind, "version": version, "body": body, "signature": signature}))
        self.state.put(f"history:{kind}", hist[-10:])
        self.state.put(f"active:{kind}", version)
        return True

    def refresh_updates(self) -> dict:
        try:
            r = self.http.get("/v1/agent/updates", headers=self._h())
            r.raise_for_status()
            latest = r.json()["latest"]
        except (httpx.HTTPError, ValueError, KeyError):
            return {"ok": False, "offline": True}
        out = {}
        for kind, u in latest.items():
            if kind == "detections" and self.state.get("active:detections") == u["version"] and self._engine:
                out[kind] = "current"
                continue
            if self.state.get(f"pinned:{kind}") and self.state.get(f"pinned:{kind}") != u["version"]:
                out[kind] = f"pinned at {self.state.get(f'pinned:{kind}')}"
                continue
            out[kind] = "installed" if self._install(kind, u["version"], u["body"], u["signature"]) else "rejected"
        return out

    def rollback(self, kind: str, version: str) -> dict:
        f = Path(self.state.root) / "updates" / f"{kind}-{version}.json"
        if f.exists():
            u = json.loads(f.read_text())
        else:
            r = self.http.get(f"/v1/agent/updates/{kind}/{version}", headers=self._h())
            if r.status_code != 200:
                return {"ok": False, "reason": "version not available"}
            u = r.json()
        if not self._install(kind, version, u["body"], u["signature"]):
            return {"ok": False, "reason": "signature verification failed"}
        self.state.put(f"pinned:{kind}", version)
        return {"ok": True, "active": version}

    @property
    def engine(self) -> Engine | None:
        if self._engine is None:
            v = self.state.get("active:detections")
            f = Path(self.state.root) / "updates" / f"detections-{v}.json"
            if v and f.exists():
                u = json.loads(f.read_text())
                if self.verifier.ok({"kind": "detections", "version": v, "body": u["body"]}, u["signature"]):
                    self._engine = Engine(u["body"], v)
        return self._engine

    # ----------------------------------------------------------------- licence
    def licence_allows_protection(self) -> bool:
        try:
            r = self.http.get("/v1/agent/licence", headers=self._h())
            r.raise_for_status()
            p = r.json()
            if self.verifier.ok(p["bundle"], p["signature"]):
                self.state.put("licence", p["bundle"]["entitlement"])
        except (httpx.HTTPError, ValueError, KeyError):
            pass  # offline: last verified entitlement applies
        ent = self.state.get("licence") or {"protection_enabled": True}
        return ent.get("protection_enabled", True)

    # ----------------------------------------------------------------- events
    def emit(self, kind: str, data: dict) -> str:
        uid = self.state.add_event(kind, data)
        eng = self.engine
        if eng and kind != "detection" and self.policy.get("behaviour_rules", True):
            for d in eng.evaluate_event(dict(data, kind=kind, event_uid=uid, ts=time.time())):
                self.state.add_event("detection", {"rule_id": d.rule_id, "rule_version": d.rule_version,
                                                   "title": d.title, "severity": d.severity,
                                                   "technique": d.technique, "evidence_event_uids": d.evidence_event_uids,
                                                   **d.matched, "action_taken": "alert"})
        return uid

    def flush(self) -> dict:
        """Replay buffered events in bounded batches; duplicates are ignored server-side."""
        sent = 0
        while True:
            batch = self.state.pending_events(500)
            if not batch:
                return {"sent": sent, "remaining": 0}
            try:
                r = self.http.post("/v1/agent/events", headers=self._h(), json={"events": [b for _, b in batch]})
                r.raise_for_status()
            except httpx.HTTPError:
                return {"sent": sent, "remaining": len(self.state.pending_events(100000)), "offline": True}
            self.state.ack_events([s for s, _ in batch])
            sent += len(batch)

    # ----------------------------------------------------------------- scanning
    def _respond_to_file(self, path: str, sha: str, d, trigger: str) -> None:
        auto_q = self.policy.get("auto_quarantine_known", True) and d.known_malware
        action = "alert"
        ev_uid = self.state.add_event("file_detected", {"path": path, "sha256": sha, "trigger": trigger})
        if auto_q:
            try:
                meta = self.vault.quarantine(path, sha, d)
                self.state.add_event("quarantine", {"local_id": meta["local_id"], "sha256": sha,
                                                    "original_path": meta["original_path"], "detection": d.title,
                                                    "rule_version": d.rule_version})
                action = "quarantined"
            except OSError as exc:
                action = f"quarantine_failed: {exc.__class__.__name__}"
        self.state.add_event("detection", {"rule_id": d.rule_id, "rule_version": d.rule_version, "title": d.title,
                                           "severity": d.severity, "technique": d.technique, "sha256": sha,
                                           "path": path, "trigger": trigger, "evidence_event_uids": [ev_uid],
                                           "action_taken": action, **{k: v for k, v in d.matched.items()
                                                                      if k not in ("sha256",)}})

    def _report_progress(self, job_group: str | None, status: str, c: dict, gaps: dict, eng) -> bool:
        """Reports to the console; returns True when the console asks the scan to stop (cancellation)."""
        if not job_group:
            return False
        try:
            r = self.http.post("/v1/agent/scan-progress", headers=self._h(), json={
                "job_group": job_group, "status": status, "files_scanned": c["scanned"],
                "archives_scanned": c["archives"], "detections": c["found"], "gaps": gaps,
                "engine_version": eng.version if eng else None})
            return bool(r.status_code == 200 and r.json().get("cancel"))
        except (httpx.HTTPError, ValueError):
            return False  # offline: keep scanning; the final result is reported on the next attempt

    def _scan_archive(self, path: Path, eng, c: dict, gaps: dict, depth: int = 0) -> list[tuple[str, object]]:
        """SEC-01 bounded archive scanning: zip/tar members up to ARCHIVE_* limits; encrypted members and
        limits reached are reported as coverage gaps, never as clean."""
        import io
        import tarfile
        import zipfile
        hits: list[tuple[str, object]] = []
        budget = {"members": 0, "bytes": 0}

        def scan_member(name: str, data: bytes) -> None:
            budget["members"] += 1
            budget["bytes"] += len(data)
            sha = hashlib.sha256(data).hexdigest()
            d = eng.scan_bytes(data, sha)
            c["scanned"] += 1
            if d:
                hits.append((f"{path}!{name}", d, sha))
            if depth < ARCHIVE_MAX_DEPTH and _archive_kind(name, data):
                inner = Path(f"{path}!{name}")
                hits.extend(self._scan_bytes_archive(inner, data, eng, c, gaps, depth + 1))

        try:
            if zipfile.is_zipfile(path):
                with zipfile.ZipFile(path) as z:
                    for info in z.infolist():
                        if info.is_dir():
                            continue
                        if budget["members"] >= ARCHIVE_MAX_MEMBERS or budget["bytes"] + info.file_size > ARCHIVE_MAX_BYTES:
                            gaps["archive_limit"] = gaps.get("archive_limit", 0) + 1
                            break
                        if info.flag_bits & 0x1:
                            gaps["encrypted_archive"] = gaps.get("encrypted_archive", 0) + 1
                            continue
                        scan_member(info.filename, z.read(info))
            elif tarfile.is_tarfile(path):
                with tarfile.open(path) as t:
                    for m in t:
                        if not m.isfile():
                            continue
                        if budget["members"] >= ARCHIVE_MAX_MEMBERS or budget["bytes"] + m.size > ARCHIVE_MAX_BYTES:
                            gaps["archive_limit"] = gaps.get("archive_limit", 0) + 1
                            break
                        f = t.extractfile(m)
                        if f:
                            scan_member(m.name, f.read())
            else:
                return hits
            c["archives"] += 1
        except (OSError, EOFError, RuntimeError, ValueError, tarfile.TarError, zipfile.BadZipFile):
            gaps["unsupported"] = gaps.get("unsupported", 0) + 1
        _ = io
        return hits

    def _scan_bytes_archive(self, label: Path, data: bytes, eng, c: dict, gaps: dict, depth: int):
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, dir=str(self.state.root)) as tmp:
            tmp.write(data)
            name = tmp.name
        try:
            hits = self._scan_archive(Path(name), eng, c, gaps, depth)
            return [(h[0].replace(name, str(label)), h[1], h[2]) for h in hits]
        finally:
            os.unlink(name)

    def scan_paths(self, paths: list[str], trigger: str = "on_demand", job_group: str | None = None,
                   max_seconds: float | None = None) -> dict:
        eng = self.engine
        c = {"scanned": 0, "found": 0, "archives": 0}
        gaps: dict[str, int] = {}
        if eng is None:
            self._report_progress(job_group, "failed", c, {"unsupported": 0}, None)
            return {"ok": False, "reason": "no verified detection bundle", "status": "failed"}
        started, last_report = time.monotonic(), time.monotonic()
        status = "running"
        self._report_progress(job_group, "running", c, gaps, eng)
        for root in paths:
            rp = Path(root)
            if not rp.exists():
                gaps["inaccessible"] = gaps.get("inaccessible", 0) + 1
                continue
            targets = [rp] if rp.is_file() else (p for p in rp.rglob("*") if p.is_file() and not p.is_symlink())
            try:
                for p in targets:
                    sp = str(p)
                    if sp.startswith(str(self.state.root)):
                        continue
                    # >= rather than >: on Windows the monotonic clock ticks every ~15 ms, so two
                    # readings in a fast loop are often equal and a strict comparison never fires.
                    if max_seconds and time.monotonic() - started >= max_seconds:
                        status = "timed_out"
                        gaps["timeout"] = gaps.get("timeout", 0) + 1
                        break
                    if job_group and time.monotonic() - last_report >= PROGRESS_SECONDS:
                        last_report = time.monotonic()
                        if self._report_progress(job_group, "running", c, gaps, eng):
                            status = "cancelled"
                            break
                    try:
                        if self.excluded(sp):
                            gaps["excluded"] = gaps.get("excluded", 0) + 1
                            continue
                        if p.stat().st_size > SCAN_SKIP_BYTES:
                            gaps["too_large"] = gaps.get("too_large", 0) + 1
                            continue
                        sha, d = eng.scan_file(sp)
                        c["scanned"] += 1
                        if d and not self.excluded(sp, sha):
                            c["found"] += 1
                            self._respond_to_file(sp, sha, d, trigger)
                            continue
                        if _archive_kind(sp, None):
                            for label, ad, asha in self._scan_archive(p, eng, c, gaps):
                                c["found"] += 1
                                # The containing archive is what can be quarantined on disk.
                                self.state.add_event("archive_member_detected", {"member": label, "sha256": asha,
                                                                                 "title": ad.title})
                                self._respond_to_file(sp, sha, ad, trigger)
                                break
                    except (OSError, PermissionError):
                        gaps["inaccessible"] = gaps.get("inaccessible", 0) + 1
            except (OSError, PermissionError):
                gaps["inaccessible"] = gaps.get("inaccessible", 0) + 1
            if status != "running":
                break
        if status == "running":
            status = "partial" if gaps.get("inaccessible") or gaps.get("archive_limit") else "complete"
        self.state.add_event("scan_completed", {"trigger": trigger, "scanned": c["scanned"], "detections": c["found"],
                                                "errors": gaps.get("inaccessible", 0), "engine_version": eng.version,
                                                "status": status, "gaps": gaps, "archives": c["archives"],
                                                "job_group": job_group})
        self._report_progress(job_group, status, c, gaps, eng)
        return {"ok": True, "status": status, "scanned": c["scanned"], "detections": c["found"],
                "errors": gaps.get("inaccessible", 0), "archives": c["archives"], "gaps": gaps}

    @staticmethod
    def default_scan_paths(scan_type: str) -> list[str]:
        home = Path.home()
        if scan_type == "full":
            if os.name == "nt":
                return [f"{d}:\\" for d in "CDEFGH" if os.path.exists(f"{d}:\\")]
            return ["/"]
        cand = [home / "Downloads", home / "Desktop", Path(os.environ.get("TEMP", "/tmp"))]
        return [str(c) for c in cand if c.exists()]

    # ----------------------------------------------------------------- monitoring
    def watch_dirs(self) -> list[str]:
        return self.state.get("watch_dirs") or self.default_scan_paths("quick")

    def tick_files(self) -> int:
        """On-download / on-access (post-write) scanning of watched directories."""
        if not (self.policy.get("on_download", True) or self.policy.get("on_access", True)):
            return 0
        eng, n = self.engine, 0
        snap: dict[str, float] = {}
        for d in self.watch_dirs():
            for p in Path(d).rglob("*"):
                try:
                    if not p.is_file() or p.is_symlink():
                        continue
                    sp, m = str(p), p.stat().st_mtime
                except OSError:
                    continue
                snap[sp] = m
                if self._file_snap.get(sp) == m:
                    continue
                if sp in self._file_snap:
                    self.emit("file_modify", {"path": sp, "pid": None})
                if eng and not self.excluded(sp):
                    try:
                        sha, det = eng.scan_file(sp)
                    except OSError:
                        continue
                    n += 1
                    if det and not self.excluded(sp, sha):
                        self._respond_to_file(sp, sha, det, "on_access")
                        snap.pop(sp, None)
        self._file_snap = snap
        return n

    def tick_processes(self) -> int:
        eng, n = self.engine, 0
        current = set()
        for proc in psutil.process_iter(["pid", "ppid", "name", "exe", "cmdline", "username"]):
            info = proc.info
            current.add(info["pid"])
            if not self._baselined or info["pid"] in self._known_pids:
                continue  # first tick records the running baseline
            try:
                parent = psutil.Process(info["ppid"]).name() if info["ppid"] else None
            except psutil.Error:
                parent = None
            data = {"pid": info["pid"], "ppid": info["ppid"], "parent": parent, "process": info["name"],
                    "image": info["exe"], "cmdline": " ".join(info["cmdline"] or []), "user": info["username"]}
            self.emit("process_start", data)
            n += 1
            if eng and info["exe"] and self.policy.get("on_execute", True) and os.path.isfile(info["exe"]):
                try:
                    sha, det = eng.scan_file(info["exe"])
                except OSError:
                    continue
                if det and not self.excluded(info["exe"], sha):
                    platform_ops.terminate(info["pid"])
                    self._respond_to_file(info["exe"], sha, det, "on_execute")
        self._known_pids = current
        self._baselined = True
        return n

    def tick_network(self) -> int:
        n = 0
        try:
            conns = psutil.net_connections(kind="inet")
        except (psutil.AccessDenied, OSError):
            return 0
        eng = self.engine
        for c in conns:
            if not c.raddr or c.status not in ("ESTABLISHED", "SYN_SENT"):
                continue
            key = (c.pid, c.laddr.ip, c.laddr.port, c.raddr.ip, c.raddr.port)
            if key in self._seen_conns:
                continue
            self._seen_conns.add(key)
            listening = {x.laddr.port for x in conns if x.status == "LISTEN"}
            direction = "inbound" if c.laddr.port in listening else "outbound"
            rep = None
            if eng and eng.check_url(f"https://{c.raddr.ip}/"):
                rep = "malicious"
            self.emit("network_connect", {"pid": c.pid, "local_ip": c.laddr.ip, "local_port": str(c.laddr.port),
                                          "remote_ip": c.raddr.ip, "remote_port": str(c.raddr.port),
                                          "direction": direction, "reputation": rep})
            n += 1
        if len(self._seen_conns) > 50000:
            self._seen_conns.clear()
        return n

    def tick_persistence(self) -> int:
        snap: dict[str, str] = {}
        for loc in platform_ops.persistence_locations():
            try:
                items = [loc] if loc.is_file() else list(loc.iterdir()) if loc.exists() else []
            except OSError:
                continue
            for it in items:
                try:
                    snap[str(it)] = str(it.stat().st_mtime)
                except OSError:
                    continue
        snap.update(platform_ops.windows_run_keys())
        changes = 0
        if self._persist_snap is not None:
            for k, v in snap.items():
                if self._persist_snap.get(k) != v:
                    self.emit("persistence_change", {"location": k, "change": "added" if k not in
                                                     self._persist_snap else "modified"})
                    changes += 1
        self._persist_snap = snap
        return changes

    def tick_removable(self) -> int:
        mounts = platform_ops.removable_mounts()
        n = 0
        if self._mounts is not None:
            for m in mounts - self._mounts:
                self.emit("removable_media", {"action": "mounted", "path": m,
                                              "policy": self.policy.get("removable_media", "audit")})
                n += 1
                if self.policy.get("removable_media") in ("audit", "block") and self.engine:
                    self.scan_paths([m], trigger="removable_media")
            for m in self._mounts - mounts:
                self.emit("removable_media", {"action": "unmounted", "path": m})
        self._mounts = mounts
        return n

    def tick_tamper(self) -> bool:
        fp = self.state.config_fingerprint()
        if fp != self._fingerprint:
            self.emit("tamper", {"action": "agent_configuration_changed"})
            self._fingerprint = fp
            return True
        return False

    # ----------------------------------------------------------------- commands
    def handle_commands(self) -> list[dict]:
        try:
            r = self.http.get("/v1/agent/commands", headers=self._h())
            r.raise_for_status()
            cmds = r.json()
        except (httpx.HTTPError, ValueError):
            return []
        results = []
        for c in cmds:
            env, sig = c["envelope"], c["signature"]
            if not self.verifier.ok(env, sig) or env["device_id"] != self.identity["device_id"] or \
                    env["tenant_id"] != self.identity["tenant_id"]:
                self.emit("tamper", {"action": "invalid_command_signature", "command_id": env.get("command_id")})
                continue
            prior = self.state.seen(env["idempotency_key"])
            if prior:
                status, result = prior["status"], dict(prior["result"], duplicate=True)
            elif not not_expired(env["expires_at"]):
                status, result = "failed", {"reason": "command expired"}
            else:
                result = self.execute(env["type"], env["params"])
                status = "acknowledged" if result.get("ok") else "failed"
                self.state.mark_seen(env["idempotency_key"], env["command_id"], status, result)
            try:
                self.http.post(f"/v1/agent/commands/{env['command_id']}/ack", headers=self._h(),
                               json={"status": status, "result": result})
            except httpx.HTTPError:
                pass  # re-delivered next poll; idempotency ledger prevents a second effect
            results.append({"command_id": env["command_id"], "status": status, "result": result})
        return results

    def execute(self, ctype: str, params: dict) -> dict:
        if ctype == "scan":
            paths = params.get("paths") or self.default_scan_paths(params.get("scan_type", "quick"))
            return self.scan_paths(paths, trigger=f"{params.get('scan_type', 'quick')}_scan",
                                   job_group=params.get("job_group"), max_seconds=params.get("max_seconds"))
        if ctype == "collect_metadata":
            out = {"ok": True, "hostname": platform.node(), "os": platform.platform(),
                   "process_count": len(psutil.pids()), "agent_version": AGENT_VERSION,
                   "buffered_bytes": self.state.buffered_bytes()}
            self.emit("metadata_collected", {k: v for k, v in out.items() if k != "ok"})
            return out
        if ctype == "terminate_process":
            res = platform_ops.terminate(params["pid"], params.get("image_sha256"))
            self.emit("process_terminated", {"pid": params["pid"], **res})
            return res
        if ctype == "isolate":
            if not self.policy.get("isolation_allowed", True):
                return {"ok": False, "reason": "device policy does not allow isolation"}
            hosts = list(self.policy.get("allowed_management_hosts", []))
            from urllib.parse import urlparse
            if self.base_url:
                hosts.append(urlparse(self.base_url).hostname or "")
            res = platform_ops.isolate([h for h in hosts if h])
            if res.get("ok"):
                self.state.put("isolation", {"expires_at": time.time() + 60 * params["expires_minutes"]})
            self.emit("isolation", {"state": "isolated" if res.get("ok") else "failed", **res})
            return res
        if ctype == "release_isolation":
            res = platform_ops.release()
            if res.get("ok"):
                self.state.put("isolation", None)
            self.emit("isolation", {"state": "released" if res.get("ok") else "release_failed", **res})
            return res
        if ctype == "quarantine":
            eng = self.engine
            if not eng:
                return {"ok": False, "reason": "no verified detection bundle"}
            sha, d = eng.scan_file(params["path"])
            if sha != params["sha256"]:
                return {"ok": False, "reason": "file changed; target mismatch"}
            from aav_detection import Detection
            d = d or Detection("manual.quarantine", eng.version, "Quarantined by authorised request", "medium")
            meta = self.vault.quarantine(params["path"], sha, d)
            self.state.add_event("quarantine", {"local_id": meta["local_id"], "sha256": sha,
                                                "original_path": meta["original_path"], "detection": d.title,
                                                "rule_version": d.rule_version})
            return {"ok": True, "local_id": meta["local_id"]}
        if ctype == "restore":
            res = self.vault.restore(params["local_id"], self.engine)
            return {"ok": res["restored"], **res}
        if ctype == "rollback_update":
            return self.rollback(params["kind"], params["version"])
        return {"ok": False, "reason": f"unsupported command {ctype}"}

    # ----------------------------------------------------------------- loop
    # ----------------------------------------------------------------- real-time blocking
    def start_realtime(self, roots: list[str] | None = None, macos_socket: str = "/var/run/aav-verdict.sock") -> str:
        """Start the platform's pre-open / pre-execute blocking backend once. Returns a status string that is
        reported in sensor health ("fanotify", "minifilter", "endpoint_security", or "unavailable: why")."""
        if self._rt is not None:
            return self._rt_status
        pol = self.policy
        block_open, block_exec = bool(pol.get("on_access", True)), bool(pol.get("on_execute", True))
        if not (block_open or block_exec):
            self._rt_status = "off (policy)"
            return self._rt_status
        from aav_agent.realtime import VerdictService
        svc = VerdictService(lambda: self.engine, self.excluded, self._respond_to_file)
        try:
            if sys.platform.startswith("linux"):
                from aav_agent.realtime_linux import FanotifyGuard
                self._rt = FanotifyGuard(svc, roots or self.watch_dirs(), block_open=block_open,
                                         block_exec=block_exec).start()
                self._rt_status = "fanotify"
            elif sys.platform == "win32":
                from aav_agent.realtime_windows import FilterPortClient
                self._rt = FilterPortClient(svc).start()
                self._rt_status = "minifilter"
            elif sys.platform == "darwin":
                from aav_agent.realtime import VerdictSocketServer
                self._rt = VerdictSocketServer(svc, macos_socket).start()
                self._rt_status = "endpoint_security"
            else:
                self._rt_status = f"unavailable: no backend for {sys.platform}"
        except Exception as exc:  # backend missing (driver not loaded, no privileges): keep user-mode detection
            self._rt, self._rt_status = None, f"unavailable: {exc}"[:200]
        if self._rt is not None:
            self._rt_service = svc
        self.emit("realtime_protection", {"status": self._rt_status})
        return self._rt_status

    def heartbeat(self) -> dict | None:
        sensors = {"file_watch": bool(self.policy.get("on_access", True)),
                   "process_monitor": bool(self.policy.get("on_execute", True)),
                   "behaviour_rules": bool(self.policy.get("behaviour_rules", True)),
                   "engine": self.engine is not None}
        status = "protected" if all(sensors.values()) else ("degraded" if self.engine else "disabled")
        if not self.licence_allows_protection():
            status = "disabled"
            sensors["licence"] = False
        sensors["realtime_blocking"] = self._rt_status       # informational: never marks the device degraded
        try:
            r = self.http.post("/v1/agent/heartbeat", headers=self._h(), json={
                "agent_version": AGENT_VERSION, "definitions_version": self.state.get("active:detections"),
                "applied_policy_version": (self.state.get("policy") or {}).get("bundle", {}).get("version"),
                "protection_status": status, "sensor_health": sensors, "posture": self.posture()})
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError:
            return None

    def probe(self, kind: str, args: dict):
        """Read-only observations used to verify an action independently of its command receipt (§3C)."""
        if kind == "isolation_active":
            return platform_ops.isolation_active()
        if kind == "pid_absent":
            pid = args.get("pid")
            return None if not isinstance(pid, int) else not psutil.pid_exists(pid)
        if kind == "path_absent":
            path = args.get("path")
            return None if not isinstance(path, str) else not os.path.exists(path)
        if kind == "vault_contains":
            return any(i["local_id"] == args.get("local_id") for i in self.vault.items())
        if kind == "vault_absent":
            return not any(i["local_id"] == args.get("local_id") for i in self.vault.items())
        return None

    def answer_probes(self, probes: list[dict]) -> int:
        answers = [{"id": p["id"], "value": self.probe(p.get("probe", ""), p.get("args") or {})}
                   for p in probes[:20] if isinstance(p, dict) and p.get("id")]
        answers = [a for a in answers if a["value"] is not None]   # unreadable state stays unverified, never guessed
        if not answers:
            return 0
        try:
            self.http.post("/v1/agent/observations", headers=self._h(), json={"observations": answers})
        except httpx.HTTPError:
            return 0
        return len(answers)

    def posture(self) -> dict:
        """SEC-05: refreshed at most hourly (the probes start OS tools)."""
        cached = self.state.get("posture") or {}
        if cached and time.time() - cached.get("_at", 0) < 3600:
            return {k: v for k, v in cached.items() if k != "_at"}
        p = platform_ops.posture()
        p["removable_media_blocked"] = bool(self.policy.get("block_removable_media", False))
        p["tamper_protection"] = bool(self.policy.get("tamper_protection", False))
        self.state.put("posture", {**p, "_at": time.time()})
        return p

    def expire_isolation(self) -> None:
        iso = self.state.get("isolation")
        if iso and iso.get("expires_at", 0) < time.time():
            res = platform_ops.release()
            self.emit("isolation", {"state": "expired_release", **res})
            if res.get("ok"):
                self.state.put("isolation", None)

    def cycle(self) -> dict:
        online = self.refresh_policy()
        self.refresh_updates()
        protect = self.licence_allows_protection()
        if protect:
            self.tick_files()
            self.tick_processes()
            self.tick_network()
            self.tick_persistence()
            self.tick_removable()
        self.tick_tamper()
        self.expire_isolation()
        cmds = self.handle_commands() if online else []
        hb = self.heartbeat()
        if hb and hb.get("probes"):
            self.answer_probes(hb["probes"])
        fl = self.flush()
        return {"online": online and hb is not None, "commands": len(cmds), "flushed": fl, "protection": protect}

    def run_forever(self, interval_s: float = 10.0) -> None:  # pragma: no cover - service loop
        try:
            p = psutil.Process()
            p.nice(10) if os.name == "posix" else p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        except (psutil.Error, AttributeError):
            pass
        self.refresh_policy()
        self.refresh_updates()
        self.start_realtime()
        while True:
            start = time.monotonic()
            try:
                self.cycle()
            except Exception as exc:
                self.state.add_event("agent_error", {"error": f"{type(exc).__name__}: {exc}"[:500]})
            time.sleep(max(1.0, interval_s - (time.monotonic() - start)))
