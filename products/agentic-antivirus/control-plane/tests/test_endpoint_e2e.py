"""End-to-end: the real endpoint agent (agent/aav_agent) against the control plane.

AV-01, AV-02, EDR-01, EDR-02, OPS-01, OPS-02, RSP-02..08, OBJ-01, OBJ-03 (benign corpus),
OBJ-06 (offline), OBJ-07, THR-06, THR-08, NFR-02 (duplicates, bounded batches)."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

from conftest import PRODUCT, eicar

sys.path.insert(0, str(PRODUCT / "agent"))

from aav_agent import platform_ops  # noqa: E402
from aav_agent.agent import Agent  # noqa: E402


@pytest.fixture
def no_firewall(monkeypatch):
    """Never touch the test host's firewall: capture the commands instead."""
    calls = []

    def fake_run(cmds):
        calls.append(cmds)
        return {"ok": True, "commands": len(cmds)}
    monkeypatch.setattr(platform_ops, "run", fake_run)
    monkeypatch.setattr(platform_ops, "_resolve", lambda hosts: ["203.0.113.10"])
    return calls


@pytest.fixture
def setup(client, new_account, invite, baseline_bundle, tmp_path):
    admin = new_account("e2e")
    analyst = invite(admin, "security_analyst")
    admin.post("/v1/policies", json={"name": "default", "body": {
        "on_access": True, "on_execute": True, "on_download": True, "auto_quarantine_known": True,
        "behaviour_rules": True, "event_buffer_mb": 64, "isolation_allowed": True,
        "allowed_management_hosts": ["console.example.com"], "tamper_protection": True}})
    token = admin.post("/v1/enrollment-tokens", json={"max_uses": 3}).json()["token"]
    agent = Agent(str(tmp_path / "state"), http=client, base_url="https://console.example.com")
    agent.enrol(token, hostname="ws-01")
    assert agent.refresh_policy() is True
    assert agent.refresh_updates()["detections"] == "installed"
    return admin, analyst, agent, tmp_path


def test_known_malware_blocked_quarantined_and_alerted(setup):
    admin, analyst, agent, tmp = setup
    work = tmp / "downloads"
    work.mkdir()
    (work / "eicar.com").write_bytes(eicar())
    (work / "embedded.bin").write_bytes(b"header" * 10 + eicar() + b"trailer")
    benign = [work / f"doc{i}.txt" for i in range(20)]
    for i, b in enumerate(benign):
        b.write_text(f"ordinary business document {i}\n" * 50)
    res = agent.scan_paths([str(work)])
    assert res["detections"] == 2 and res["scanned"] == 22
    assert not (work / "eicar.com").exists() and not (work / "embedded.bin").exists()  # quarantined
    assert all(b.exists() for b in benign)  # benign corpus untouched (OBJ-03)
    assert agent.flush()["remaining"] == 0
    alerts = admin.get("/v1/alerts").json()
    titles = {a["rule_id"] for a in alerts}
    assert {"sig.eicar.sha256", "sig.eicar.bytes"} <= titles
    a = next(x for x in alerts if x["rule_id"] == "sig.eicar.sha256")
    assert a["action_taken"] == "quarantined" and a["rule_version"] == "2026.11.18-1" and a["evidence_event_ids"]
    q = admin.get("/v1/quarantine").json()
    assert len(q) == 2 and {i["status"] for i in q} == {"quarantined"}
    inc = admin.get("/v1/incidents").json()
    assert inc and inc[0]["alert_count"] >= 2
    timeline = admin.get(f"/v1/incidents/{inc[0]['id']}").json()["timeline"]
    assert any(t["type"] == "event" for t in timeline) and any(t["type"] == "alert" for t in timeline)
    assert any(n["kind"] == "alert.high" for n in admin.get("/v1/notifications").json())


def test_restore_requires_admin_reason_and_clean_rescan(setup):
    admin, analyst, agent, tmp = setup
    f = tmp / "x.com"
    f.write_bytes(eicar())
    agent.scan_paths([str(f)])
    agent.flush()
    item = admin.get("/v1/quarantine").json()[0]
    assert analyst.post(f"/v1/quarantine/{item['id']}/restore", json={"reason": "needed"}).status_code == 403
    assert admin.post(f"/v1/quarantine/{item['id']}/restore", json={"reason": ""}).status_code == 422
    r = admin.post(f"/v1/quarantine/{item['id']}/restore", json={"reason": "vendor confirmed false positive"})
    assert r.status_code == 201 and r.json()["status"] == "approved", r.text
    out = agent.handle_commands()
    assert out[0]["status"] == "failed" and out[0]["result"]["rescan"]["clean"] is False  # still malicious
    assert not f.exists()
    item = admin.get("/v1/quarantine").json()[0]
    assert item["status"] == "quarantined" and item["restore_scan"]["clean"] is False
    acts = [e["action"] for e in admin.get("/v1/audit").json()]
    assert "command.ack" in acts and "action.dispatch" in acts


def test_manual_quarantine_then_clean_restore(setup):
    admin, analyst, agent, tmp = setup
    f = tmp / "report.txt"
    f.write_text("benign quarterly report")
    sha = hashlib.sha256(f.read_bytes()).hexdigest()
    dev = admin.get("/v1/devices").json()[0]["id"]
    r = analyst.post("/v1/actions", json={"action_type": "quarantine_file", "targets": [dev],
                                          "params": {"path": str(f), "sha256": sha}, "reason": "suspicious"})
    assert r.json()["status"] == "proposed"  # not a known-malware match -> approval
    rid = r.json()["id"]
    assert analyst.post(f"/v1/actions/{rid}/approve", json={}).status_code == 200
    assert analyst.post(f"/v1/actions/{rid}/dispatch").json()["status"] == "dispatched"
    assert agent.handle_commands()[0]["status"] == "acknowledged" and not f.exists()
    agent.flush()
    item = next(i for i in admin.get("/v1/quarantine").json() if i["sha256"] == sha)
    admin.post(f"/v1/quarantine/{item['id']}/restore", json={"reason": "analyst cleared it"})
    assert agent.handle_commands()[0]["status"] == "acknowledged"
    assert f.read_text() == "benign quarterly report"
    assert next(i for i in admin.get("/v1/quarantine").json() if i["sha256"] == sha)["status"] == "restored"


def test_behaviour_detection_links_evidence(setup):
    admin, analyst, agent, tmp = setup
    uid = agent.emit("process_start", {"pid": 4242, "ppid": 1, "process": "powershell.exe", "parent": "winword.exe",
                                       "cmdline": "powershell.exe -enc SQBFAFgAIAAoAE4AZQB3AC0ATwBiAGoAZQBjAHQA"})
    for i in range(50):
        agent.emit("file_modify", {"path": f"C:/Users/a/doc{i}.docx.locked", "pid": 777})
    agent.emit("process_start", {"pid": 99, "process": "vssadmin.exe", "cmdline": "vssadmin delete shadows /all /quiet"})
    agent.flush()
    alerts = {a["rule_id"]: a for a in admin.get("/v1/alerts").json()}
    assert {"beh.script.encoded_powershell", "beh.ransom.mass_modify", "beh.ransom.shadow_delete"} <= set(alerts)
    assert len(alerts["beh.ransom.mass_modify"]["evidence_event_ids"]) >= 50
    inc = admin.get("/v1/incidents").json()[0]
    assert inc["severity"] == "critical"
    _ = uid


def test_containment_isolation_preserves_management_and_releases(setup, no_firewall):
    admin, analyst, agent, tmp = setup
    dev = admin.get("/v1/devices").json()[0]["id"]
    r = analyst.post("/v1/actions", json={"action_type": "isolate_device", "targets": [dev],
                                          "params": {"expires_minutes": 60}, "reason": "ransomware"})
    rid = r.json()["id"]
    assert r.json()["status"] == "proposed"
    assert analyst.post(f"/v1/actions/{rid}/dispatch").status_code == 409  # not approved
    analyst.post(f"/v1/actions/{rid}/approve", json={})
    d1 = analyst.post(f"/v1/actions/{rid}/dispatch").json()
    d2 = analyst.post(f"/v1/actions/{rid}/dispatch").json()
    assert d2["duplicate"] is True and d1["commands"][0]["command_id"] == d2["commands"][0]["command_id"]
    out = agent.handle_commands()
    assert len(out) == 1 and out[0]["status"] == "acknowledged"
    rules = " ".join(" ".join(c) for c in no_firewall[0])
    assert "203.0.113.10" in rules and "policy drop" in rules  # management path kept, rest dropped
    devrow = admin.get("/v1/devices").json()[0]
    assert devrow["isolation_state"] == "isolated" and devrow["isolation_expires_at"]
    assert admin.get(f"/v1/actions/{rid}/outcomes").json()[0]["status"] == "acknowledged"
    rel = analyst.post("/v1/actions", json={"action_type": "release_isolation", "targets": [dev], "params": {}})
    analyst.post(f"/v1/actions/{rel.json()['id']}/approve", json={})
    analyst.post(f"/v1/actions/{rel.json()['id']}/dispatch")
    assert agent.handle_commands()[0]["status"] == "acknowledged"
    assert admin.get("/v1/devices").json()[0]["isolation_state"] == "none"


def test_duplicate_command_delivery_has_one_effect(setup, no_firewall, monkeypatch):
    admin, analyst, agent, tmp = setup
    dev = admin.get("/v1/devices").json()[0]["id"]
    rid = analyst.post("/v1/actions", json={"action_type": "isolate_device", "targets": [dev],
                                            "params": {"expires_minutes": 5}}).json()["id"]
    analyst.post(f"/v1/actions/{rid}/approve", json={})
    analyst.post(f"/v1/actions/{rid}/dispatch")
    cmds = agent.http.get("/v1/agent/commands", headers=agent._h()).json()
    # deliver the same signed command twice (e.g. lost ack)
    orig = agent.http.get
    monkeypatch.setattr(agent.http, "get", lambda url, **kw: type("R", (), {
        "raise_for_status": lambda s: None, "json": lambda s: cmds + cmds})() if url == "/v1/agent/commands"
        else orig(url, **kw))
    out = agent.handle_commands()
    assert len(out) == 2 and out[1]["result"].get("duplicate") is True
    assert len(no_firewall) == 1  # one effective action


def test_offline_enforcement_buffer_and_replay(setup, client):
    admin, analyst, agent, tmp = setup
    import httpx
    offline = Agent(str(Path(agent.state.root)), http=httpx.Client(base_url="http://127.0.0.1:9", timeout=0.5))
    assert offline.refresh_policy() is False
    assert offline.policy["auto_quarantine_known"] is True  # last verified policy still enforced
    f = tmp / "offline.com"
    f.write_bytes(eicar())
    assert offline.scan_paths([str(f)])["detections"] == 1 and not f.exists()
    assert offline.flush()["offline"] is True and offline.state.buffered_bytes() > 0
    batch = [b for _, b in offline.state.pending_events(1000)]
    online = Agent(str(Path(agent.state.root)), http=client)
    assert online.flush()["remaining"] == 0
    r = client.post("/v1/agent/events", headers=online._h(), json={"events": batch})  # replay again
    assert r.json()["accepted"] == 0 and r.json()["duplicates"] == len(batch)


def test_event_buffer_respects_size_limit(setup):
    admin, analyst, agent, tmp = setup
    pol = agent.state.get("policy")
    pol["bundle"]["body"]["event_buffer_mb"] = 1
    agent.state.put("policy", pol)
    for i in range(3000):
        agent.state.add_event("process_start", {"pid": i, "cmdline": "x" * 500})
    assert agent.state.buffered_bytes() <= 1024 * 1024
    assert int(agent.state.get("dropped_events")) > 0


def test_unsigned_or_tampered_updates_rejected_and_rollback(setup, client):
    admin, analyst, agent, tmp = setup
    data = json.loads((PRODUCT / "detection" / "rules" / "baseline.json").read_text())
    good_sig = client.get("/v1/agent/updates", headers=agent._h()).json()["latest"]["detections"]["signature"]
    assert agent._install("detections", "evil-1", {"hash_signatures": []}, good_sig) is False  # body changed
    agent.flush()
    assert any(a["rule_id"] == "beh.tamper.agent" for a in admin.get("/v1/alerts").json())
    assert agent.state.get("active:detections") == data["version"]
    v2 = dict(data["body"], hash_signatures=data["body"]["hash_signatures"] + [
        {"id": "sig.test.v2", "sha256": "a" * 64, "name": "v2 test", "severity": "low"}])
    assert admin.post("/v1/updates", json={"kind": "detections", "version": "2026.11.18-2", "body": v2}).status_code == 201
    assert agent.refresh_updates()["detections"] == "installed"
    assert agent.engine.version == "2026.11.18-2"
    dev = admin.get("/v1/devices").json()[0]["id"]
    rid = analyst.post("/v1/actions", json={"action_type": "rollback_update", "targets": [dev],
                                            "params": {"kind": "detections", "version": data["version"]}}).json()["id"]
    ap = analyst.post(f"/v1/actions/{rid}/approve", json={})
    dp = analyst.post(f"/v1/actions/{rid}/dispatch")
    assert dp.status_code == 200, (ap.text, dp.text)
    assert agent.handle_commands()[0]["status"] == "acknowledged"
    assert agent.engine.version == data["version"]
    assert agent.refresh_updates()["detections"].startswith("pinned")
    admin.post("/v1/updates/detections/2026.11.18-2/revoke")


def test_invalid_policy_signature_keeps_last_verified(setup, monkeypatch):
    admin, analyst, agent, tmp = setup
    before = agent.state.get("policy")
    orig = agent.http.get

    def tampered(url, **kw):
        r = orig(url, **kw)
        if url == "/v1/agent/policy":
            body = r.json()
            body["bundle"]["body"]["auto_quarantine_known"] = False
            return type("R", (), {"raise_for_status": lambda s: None, "json": lambda s: body})()
        return r
    monkeypatch.setattr(agent.http, "get", tampered)
    assert agent.refresh_policy() is False
    assert agent.state.get("policy") == before


def test_inventory_flags_stale_disabled_outdated(setup):
    admin, analyst, agent, tmp = setup
    agent.heartbeat()
    dev = admin.get("/v1/devices").json()[0]
    assert dev["protection_status"] == "protected" and dev["issues"] == []
    admin.post("/v1/policies", json={"name": "default", "body": {"on_access": True}})  # new version -> outdated
    pol = agent.state.get("policy")
    pol["bundle"]["body"]["on_access"] = False  # sensor disabled locally
    agent.state.put("policy", pol)
    agent.heartbeat()
    dev = admin.get("/v1/devices").json()[0]
    assert "outdated_policy" in dev["issues"] and "sensor_disabled" in dev["issues"]
    assert dev["protection_status"] == "degraded"
    assert any(n["kind"] == "device.degraded" for n in admin.get("/v1/notifications").json())


def test_removable_media_and_tamper_events(setup, monkeypatch):
    admin, analyst, agent, tmp = setup
    mounts = [set(), {"/media/usb0"}]
    monkeypatch.setattr(platform_ops, "removable_mounts", lambda: mounts.pop(0) if mounts else {"/media/usb0"})
    agent.tick_removable()
    assert agent.tick_removable() == 1
    (Path(agent.state.root) / "identity.json").write_text("{}")
    assert agent.tick_tamper() is True
    agent.flush()
    rules = {a["rule_id"] for a in admin.get("/v1/alerts").json()}
    assert {"beh.media.removable_mounted", "beh.tamper.agent"} <= rules


def test_scheduled_scans_are_delivered_in_signed_policy(setup):
    admin, analyst, agent, tmp = setup
    assert admin.post("/v1/scan-schedules", json={"policy_name": "default", "scan_type": "full",
                                                  "cron": "0 2 * * 0"}).status_code == 201
    admin.post("/v1/exclusions", json={})  # no direct create: exclusions go through the catalogue
    rid = admin.post("/v1/actions", json={"action_type": "add_exclusion", "targets": ["tenant"],
                                          "params": {"kind": "path", "value": "/opt/build/*"},
                                          "reason": "build cache"}).json()
    assert rid["status"] == "approved" and rid["dispatch"]["status"] == "completed"
    assert agent.refresh_policy()
    b = agent.state.get("policy")["bundle"]
    assert b["schedules"] == [{"scan_type": "full", "cron": "0 2 * * 0"}]
    assert agent.excluded("/opt/build/a.o")
