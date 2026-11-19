"""Release-1 acceptance evidence for register items that previously had no automated test.

OBJ-03  false positives on a benign corpus (D-05 R1 corpus: OS-installed files + generated office documents)
OBJ-05  agent CPU overhead during an office-like workload, excluding scheduled full scans
THR-05  cloud audit findings ingested, owned, remediation needs authorisation
THR-07  DLP unusual access/transfer flagged and attributed
DDOS-02 connection saturation / packet rate / origin health monitored
DDOS-04 authoritative DNS and origin-bypass alerts raised
DDL-03  per-service availability, latency and success thresholds defined and audited
"""
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil
import pytest

from conftest import PRODUCT, eicar

sys.path.insert(0, str(PRODUCT / "agent"))

from aav_agent.agent import Agent  # noqa: E402
from aav_detection.engine import Engine  # noqa: E402


# ---------------------------------------------------------------- OBJ-03
def _benign_corpus(tmp: Path) -> list[Path]:
    files: list[Path] = []
    for root in ("/usr/bin", "/usr/lib/python3", "/usr/share/doc"):
        for d, _, fs in os.walk(root):
            for f in fs:
                p = Path(d) / f
                if p.is_file() and not p.is_symlink():
                    files.append(p)
                if len(files) >= 5000:
                    break
            if len(files) >= 5000:
                break
    office = tmp / "office"
    office.mkdir()
    for i in range(500):
        p = office / f"report-{i}.{('docx', 'xlsx', 'pdf', 'txt', 'csv')[i % 5]}"
        p.write_bytes((f"Quarterly report {i}; invoice; macro; powershell; password policy\n" * 40).encode())
        files.append(p)
    return files


def test_false_positive_rate_below_half_percent_on_benign_corpus(baseline_bundle, tmp_path):
    eng = Engine(baseline_bundle["body"], baseline_bundle["version"])
    corpus = _benign_corpus(tmp_path)
    assert len(corpus) >= 1000
    fps = [str(p) for p in corpus if eng.scan_file(str(p))[1]]
    assert 100 * len(fps) / len(corpus) < 0.5, fps[:10]
    pos = tmp_path / "positive.com"
    pos.write_bytes(eicar())
    assert eng.scan_file(str(pos))[1] is not None  # positive control: the corpus run is not vacuous


# ---------------------------------------------------------------- OBJ-05
@pytest.fixture
def agent(client, new_account, baseline_bundle, tmp_path):
    admin = new_account("perf")
    admin.post("/v1/policies", json={"name": "default", "body": {
        "on_access": True, "on_execute": True, "on_download": True, "auto_quarantine_known": True,
        "behaviour_rules": True, "event_buffer_mb": 64}})
    token = admin.post("/v1/enrollment-tokens", json={}).json()["token"]
    a = Agent(str(tmp_path / "state"), http=client, base_url="https://console.example.com")
    a.enrol(token, hostname="perf-01")
    a.refresh_policy()
    a.refresh_updates()
    return a


def test_agent_cpu_overhead_below_3_points_during_office_workload(agent, tmp_path):
    """Local collector CPU per 10 s cycle (the shipped interval) as a share of total machine CPU."""
    docs = tmp_path / "Documents"
    docs.mkdir()
    for i in range(1500):
        (docs / f"f{i}.txt").write_text("draft text\n" * 200)
    agent.state.put("watch_dirs", [str(docs)])
    ticks = (agent.tick_files, agent.tick_processes, agent.tick_network, agent.tick_persistence,
             agent.tick_removable)
    for t in ticks:  # baseline pass (first tick records the running state)
        t()
    cpu, cycles, interval = 0.0, 12, 10.0
    for c in range(cycles):
        for i in range(25):  # office workload: edit and save 25 documents per cycle
            (docs / f"f{(c * 25 + i) % 1500}.txt").write_text(f"edit {c}\n" * 220)
        (docs / f"new-{c}.txt").write_text("new memo\n" * 50)
        subprocess.run([sys.executable, "-c", "pass"], check=True)  # a process start per cycle
        start = time.thread_time()
        for t in ticks:
            t()
        cpu += time.thread_time() - start
    pct = 100 * (cpu / cycles) / interval / (psutil.cpu_count() or 1)
    print(f"OBJ-05 agent overhead {pct:.3f} percentage points ({cpu / cycles * 1000:.1f} ms CPU per cycle, "
          f"{psutil.cpu_count()} CPUs)")
    assert pct < 3.0


# ---------------------------------------------------------------- THR / DDoS monitoring
@pytest.fixture
def org(new_account, invite, enrol):
    admin = new_account("r1")
    analyst = invite(admin, "security_analyst")
    dev = enrol(admin, "ws-r1", "windows")
    return admin, analyst, dev


def _integration(admin, kind):
    body = admin.post("/v1/integrations", json={"name": f"{kind}-r1", "signal_kind": kind,
                                                "protocol": "webhook"}).json()
    r = admin.post(f"/v1/integrations/{body['id']}/maturity",
                   json={"maturity": "test_only", "provider": "acme", "evidence": {}})
    assert r.status_code == 200, r.text
    return body


def _ingest(client, integ, xid, category, **kw):
    payload = {"external_id": xid, "category": category, "severity": kw.pop("severity", "high"),
               "observed_at": datetime.now(timezone.utc).isoformat(), **kw}
    r = client.post(f"/v1/ingest/{integ['id']}", headers={"X-AAV-Webhook-Secret": integ["webhook_secret"]},
                    json=payload)
    assert r.status_code == 202, r.text
    return r.json()


@pytest.mark.parametrize("kind,categories", [
    ("cloud_audit", ["risky_config_change", "suspicious_key_use", "privilege_escalation"]),  # THR-05
    ("dlp", ["unusual_access", "unusual_transfer"]),  # THR-07
])
def test_cloud_and_insider_findings_owned_and_remediation_needs_authorisation(org, client, kind, categories):
    admin, analyst, dev = org
    integ = _integration(admin, kind)
    for i, cat in enumerate(categories):
        body = _ingest(client, integ, f"{kind}-{i}", cat, device_hostname="ws-r1", user_ref="bob@example.com")
        assert body["incident_id"] and body["simulation"] is True and body["device_id"] == dev["device_id"]
        inc = admin.get(f"/v1/incidents/{body['incident_id']}").json()
        assert any(t["type"] == "external_alert" for t in inc["timeline"])
    # remediation is a governed action: an analyst proposal is not executed without approval
    r = analyst.post("/v1/actions", json={"action_type": "suspend_account", "targets": ["bob@example.com"],
                                          "params": {"integration_id": integ["id"]},
                                          "incident_id": body["incident_id"]})
    assert r.status_code in (200, 201) and r.json()["status"] == "proposed"
    audit = admin.get("/v1/audit").json()
    rows = audit["items"] if isinstance(audit, dict) else audit
    assert any(a["action"] == "signal.ingest" for a in rows)


def test_protocol_exhaustion_and_dns_origin_signals_monitored(org, client):
    admin, analyst, dev = org
    admin.post("/v1/assets", json={"kind": "hostname", "value": "app.example.com", "service": "app",
                                   "provider": "upstream-x", "mitigation_policy": "always-on"})
    lb, dns, cdn = (_integration(admin, k) for k in ("load_balancer", "dns", "cdn"))
    a = _ingest(client, lb, "lb-1", "connection_saturation", asset="app.example.com", severity="critical")
    _ingest(client, lb, "lb-2", "packet_rate", asset="app.example.com")
    _ingest(client, lb, "lb-3", "origin_unhealthy", asset="app.example.com")  # DDOS-02
    _ingest(client, dns, "dns-1", "authoritative_unavailable", asset="app.example.com", severity="critical")
    _ingest(client, cdn, "cdn-1", "origin_bypass", asset="app.example.com")  # DDOS-04
    st = admin.get("/v1/ddos/status").json()
    assert "app.example.com" in st["affected_assets"]
    inc = admin.get(f"/v1/incidents/{a['incident_id']}").json()
    cats = {t["category"] for t in inc["timeline"] if t["type"] == "external_alert"}
    assert {"connection_saturation", "packet_rate", "origin_unhealthy", "authoritative_unavailable",
            "origin_bypass"} <= cats  # all correlated to one incident for the asset
    kinds = {n["kind"] for n in admin.get("/v1/notifications").json()}
    assert {"load_balancer.critical", "dns.critical"} <= kinds


def test_service_objectives_defined_and_audited(org):
    admin, analyst, dev = org
    r = admin.post("/v1/service-objectives", json={"service": "app", "availability_pct": 99.9,
                                                   "latency_p95_ms": 400, "success_rate_pct": 99.5})
    assert r.status_code == 201, r.text
    slo = [s for s in admin.get("/v1/service-objectives").json() if s["service"] == "app"][0]
    assert float(slo["availability_pct"]) == 99.9 and slo["latency_p95_ms"] == 400
    assert analyst.post("/v1/service-objectives", json={"service": "x", "availability_pct": 1,
                                                        "latency_p95_ms": 1, "success_rate_pct": 1}).status_code == 403
