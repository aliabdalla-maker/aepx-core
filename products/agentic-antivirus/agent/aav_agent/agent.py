"""User-mode endpoint agent.

Trace: ARC-01, AV-01 (on-demand, quick/full/scheduled, on-download/on-access via file watching,
on-execute via new-process image scanning), AV-02, EDR-01, EDR-02, OPS-02, RSP-02, RSP-08,
THR-06 (reject unsigned updates), THR-08 (removable media, tamper), OBJ-06.

Limitation (register B-01): in user mode, "on access" and "on execute" detect and respond
immediately after the file is written or the process starts; pre-open / pre-execution blocking
needs the kernel minifilter (Windows) / Endpoint Security entitlement (macOS) / fanotify
permission events (Linux), which are not part of this package.
"""
from __future__ import annotations

import fnmatch
import json
import os
import platform
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

AGENT_VERSION = "0.1.0"
SCAN_SKIP_BYTES = 256 * 1024 * 1024


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

    def scan_paths(self, paths: list[str], trigger: str = "on_demand") -> dict:
        eng = self.engine
        if eng is None:
            return {"ok": False, "reason": "no verified detection bundle"}
        scanned, found, errors = 0, 0, 0
        for root in paths:
            rp = Path(root)
            targets = [rp] if rp.is_file() else (p for p in rp.rglob("*") if p.is_file() and not p.is_symlink())
            for p in targets:
                sp = str(p)
                if sp.startswith(str(self.state.root)):
                    continue
                try:
                    if p.stat().st_size > SCAN_SKIP_BYTES or self.excluded(sp):
                        continue
                    sha, d = eng.scan_file(sp)
                    scanned += 1
                    if d and not self.excluded(sp, sha):
                        found += 1
                        self._respond_to_file(sp, sha, d, trigger)
                except (OSError, PermissionError):
                    errors += 1
        self.state.add_event("scan_completed", {"trigger": trigger, "scanned": scanned, "detections": found,
                                                "errors": errors, "engine_version": eng.version})
        return {"ok": True, "scanned": scanned, "detections": found, "errors": errors}

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
            return self.scan_paths(paths, trigger=f"{params.get('scan_type', 'quick')}_scan")
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
    def heartbeat(self) -> dict | None:
        sensors = {"file_watch": bool(self.policy.get("on_access", True)),
                   "process_monitor": bool(self.policy.get("on_execute", True)),
                   "behaviour_rules": bool(self.policy.get("behaviour_rules", True)),
                   "engine": self.engine is not None}
        status = "protected" if all(sensors.values()) else ("degraded" if self.engine else "disabled")
        if not self.licence_allows_protection():
            status = "disabled"
            sensors["licence"] = False
        try:
            r = self.http.post("/v1/agent/heartbeat", headers=self._h(), json={
                "agent_version": AGENT_VERSION, "definitions_version": self.state.get("active:detections"),
                "applied_policy_version": (self.state.get("policy") or {}).get("bundle", {}).get("version"),
                "protection_status": status, "sensor_health": sensors})
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError:
            return None

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
        fl = self.flush()
        return {"online": online and hb is not None, "commands": len(cmds), "flushed": fl, "protection": protect}

    def run_forever(self, interval_s: float = 10.0) -> None:  # pragma: no cover - service loop
        try:
            p = psutil.Process()
            p.nice(10) if os.name == "posix" else p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        except (psutil.Error, AttributeError):
            pass
        while True:
            start = time.monotonic()
            try:
                self.cycle()
            except Exception as exc:
                self.state.add_event("agent_error", {"error": f"{type(exc).__name__}: {exc}"[:500]})
            time.sleep(max(1.0, interval_s - (time.monotonic() - start)))
