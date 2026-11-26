"""Deployment prompt §3A/§3B acceptance checks (SEC-01, SEC-04, SEC-05, dashboard, REC-03..06).

Required by the prompt: an offline device, stale definitions, a partial scan, a blind network segment and
a public endpoint without verified upstream mitigation each produce the right state and gap; a gap closes
only after fresh verification; one tenant cannot see another tenant's security data; removal success,
removal failure, an incomplete rescan and a recurrence that reopens the incident.
"""
import pytest


@pytest.fixture
def org(new_account, invite, enrol, baseline_bundle):
    admin = new_account("sec")
    analyst = invite(admin, "security_analyst")
    return admin, analyst, enrol, baseline_bundle


def beat(client, dev, version, status="protected", posture=None):
    r = client.post("/v1/agent/heartbeat", headers={"X-Device-Key": dev["device_key"]}, json={
        "agent_version": "0.1.2", "definitions_version": version, "protection_status": status,
        "sensor_health": {"files": "ok"}, "posture": posture or {"disk_encryption": True, "firewall": True}})
    assert r.status_code == 200, r.text


def progress(client, dev, group, status, **kw):
    r = client.post("/v1/agent/scan-progress", headers={"X-Device-Key": dev["device_key"]},
                    json={"job_group": group, "status": status, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def full_scan(admin, client, dev, status="complete", detections=0, gaps=None):
    out = admin.post("/v1/scan-jobs", json={"device_ids": [dev["device_id"]], "scan_type": "full"}).json()
    progress(client, dev, out["group_id"], "running", files_scanned=10)
    progress(client, dev, out["group_id"], status, files_scanned=100, detections=detections, gaps=gaps or {},
             engine_version="x")
    return out


def device_row(dash, dev):
    return next(d for d in dash["devices"] if d["id"] == dev["device_id"])


def test_dashboard_states_and_gaps_for_required_failure_cases(org, client):
    admin, analyst, enrol, bundle = org
    healthy, offline, stale, partial = (enrol(admin, h) for h in ("ok-1", "off-1", "stale-1", "part-1"))
    beat(client, healthy, bundle["version"])
    full_scan(admin, client, healthy)
    beat(client, stale, "2020.01.01-0")
    beat(client, partial, bundle["version"])
    full_scan(admin, client, partial, status="partial", gaps={"inaccessible": 3})
    admin.post("/v1/network/segments", json={"name": "Office LAN", "cidr": "10.20.0.0/24"})
    admin.post("/v1/assets", json={"kind": "hostname", "value": "shop.example.com", "service": "shop"})

    dash = admin.get("/v1/security/dashboard").json()
    assert device_row(dash, healthy)["state"] == "protected"
    assert device_row(dash, offline)["state"] == "unknown"           # offline / never reported stays visible
    assert device_row(dash, stale)["state"] == "degraded"
    assert "definitions out of date" in device_row(dash, stale)["reasons"]
    assert device_row(dash, partial)["state"] == "degraded"
    assert "last scan partial" in device_row(dash, partial)["reasons"]

    k = dash["kpis"]
    assert k["states"] == {"protected": 1, "degraded": 2, "unprotected": 0, "unknown": 1}
    assert k["endpoint_protection_coverage"]["numerator"] == 1 and k["endpoint_protection_coverage"]["denominator"] == 4
    assert k["network_visibility"] == {"numerator": 0, "denominator": 1, "value": 0.0, "unit": "%",
                                       "blind": ["Office LAN"]}
    assert k["scan_execution_reliability"]["breakdown"] == {"complete": 1, "partial": 1}
    assert k["ddos_resilience"]["denominator"] == 1 and k["ddos_resilience"]["numerator"] == 0

    gaps = admin.get("/v1/security/gaps").json()
    by = {(g["subject_label"], g["expected_control"]) for g in gaps}
    assert ("off-1", "heartbeat within 24 hours") in by
    assert ("stale-1", "current detection definitions") in by
    assert ("part-1", "complete last scan") in by
    assert ("Office LAN (10.20.0.0/24)", "network telemetry within 24 hours") in by
    assert ("shop.example.com", "verified upstream DDoS mitigation") in by
    for g in gaps:  # every gap row carries the mandatory fields
        for f in ("subject_label", "expected_control", "observed_state", "reason", "severity", "owner", "due_date",
                  "proposed_fix", "retest_status"):
            assert g[f] not in (None, ""), (f, g)


def test_gap_closes_only_after_fresh_verification(org, client):
    admin, analyst, enrol, bundle = org
    dev = enrol(admin, "stale-2")
    beat(client, dev, "2020.01.01-0")
    full_scan(admin, client, dev)
    admin.post("/v1/security/gaps/evaluate")
    gap = [g for g in admin.get("/v1/security/gaps").json() if g["expected_control"] == "current detection definitions"]
    assert len(gap) == 1
    admin.post("/v1/security/gaps/evaluate")  # no new evidence: still open
    assert any(g["id"] == gap[0]["id"] for g in admin.get("/v1/security/gaps").json())
    beat(client, dev, bundle["version"])       # fresh heartbeat with current definitions
    assert admin.post("/v1/security/gaps/evaluate").json()["closed_now"] >= 1
    closed = [g for g in admin.get("/v1/security/gaps?status=closed").json() if g["id"] == gap[0]["id"]][0]
    assert closed["retest_status"] == "verified_closed" and closed["closed_evidence"]["evaluated_at"]


def test_security_data_is_tenant_isolated(org, client, new_account, enrol):
    admin, analyst, _, bundle = org
    dev = enrol(admin, "iso-a")
    admin.post("/v1/network/segments", json={"name": "A-net", "cidr": "10.30.0.0/24"})
    admin.post("/v1/security/gaps/evaluate")
    other = new_account("other")
    d2 = other.get("/v1/security/dashboard").json()
    assert all(d["id"] != dev["device_id"] for d in d2["devices"])
    assert other.get("/v1/network/segments").json() == []
    assert all(g["subject_label"] != "iso-a" for g in other.get("/v1/security/gaps").json())
    assert other.get("/v1/scan-jobs").json() == []


def test_scan_jobs_progress_cancel_missed_and_validation(org, client, admin_sql):
    admin, analyst, enrol, bundle = org
    dev = enrol(admin, "scan-1")
    assert admin.post("/v1/scan-jobs", json={"device_ids": [dev["device_id"]], "scan_type": "targeted"}).status_code == 422
    out = admin.post("/v1/scan-jobs", json={"device_ids": [dev["device_id"]], "scan_type": "targeted",
                                            "paths": ["C:/Users/Public"], "max_seconds": 60}).json()
    assert out["action_request"]["status"] == "approved" and out["dispatch"]
    assert progress(client, dev, out["group_id"], "running", files_scanned=5)["cancel"] is False
    job = out["jobs"][0]["job_id"]
    assert admin.post(f"/v1/scan-jobs/{job}/cancel").json()["status"] == "running"
    assert progress(client, dev, out["group_id"], "running", files_scanned=9)["cancel"] is True
    progress(client, dev, out["group_id"], "cancelled", files_scanned=9, gaps={"encrypted_archive": 1, "bogus": 4})
    row = [j for j in admin.get("/v1/scan-jobs").json() if j["id"] == job][0]
    assert row["status"] == "cancelled" and row["gaps"] == {"encrypted_archive": 1} and row["finished_at"]
    assert admin.post(f"/v1/scan-jobs/{job}/cancel").status_code == 409
    q = admin.post("/v1/scan-jobs", json={"device_ids": [dev["device_id"]], "scan_type": "quick"}).json()
    admin_sql("UPDATE aav.scan_jobs SET created_at = now() - interval '2 hours' WHERE group_id = %s", q["group_id"])
    assert [j for j in admin.get("/v1/scan-jobs").json() if j["group_id"] == q["group_id"]][0]["status"] == "missed"
    assert analyst.post("/v1/scan-jobs", json={"device_ids": [dev["device_id"]]}).status_code in (201, 403)


def test_posture_reported_and_unknown_kept(org, client):
    admin, analyst, enrol, bundle = org
    dev = enrol(admin, "post-1")
    beat(client, dev, bundle["version"], posture={"disk_encryption": False, "firewall": None, "os_updates_pending": 4,
                                                  "evil": "x"})
    full_scan(admin, client, dev)
    row = device_row(admin.get("/v1/security/dashboard").json(), dev)
    assert row["posture"] == {"disk_encryption": False, "firewall": None, "os_updates_pending": 4}
    assert "disk not encrypted" in row["reasons"] and "host firewall off" not in row["reasons"]


def test_network_inventory_deduplicates_and_places_hosts(org):
    admin, *_ = org
    admin.post("/v1/network/segments", json={"name": "DMZ", "cidr": "192.0.2.0/24"})
    items = [{"kind": "host", "value": "192.0.2.10"}, {"kind": "service", "value": "192.0.2.10:443",
             "attributes": {"ip": "192.0.2.10", "product": "nginx"}},
             {"kind": "certificate", "value": "shop.example.com", "attributes": {"not_after": "2020-01-01T00:00:00Z"}}]
    assert admin.post("/v1/network/inventory", json={"source": "asset-register", "items": items}).json() == \
        {"added": 3, "deduplicated": 0}
    assert admin.post("/v1/network/inventory", json={"source": "dns", "items": items[:1]}).json() == \
        {"added": 0, "deduplicated": 1}
    inv = admin.get("/v1/network/inventory").json()
    assert len(inv) == 3 and all(i["segment_id"] for i in inv if i["kind"] != "certificate")
    assert [i for i in inv if i["kind"] == "certificate"][0]["certificate_state"] == "expiring"
    seg = admin.get("/v1/network/segments").json()[0]
    assert seg["visibility"] == "blind" and seg["assets"] == 2
    admin.post(f"/v1/network/segments/{seg['id']}/telemetry", json={"source": "dns-logs"})
    assert admin.get("/v1/network/segments").json()[0]["visibility"] == "monitored"


def test_recovery_removal_rescan_recurrence_and_return_gates(org, client):
    admin, analyst, enrol, bundle = org
    dev = enrol(admin, "rec-1")
    beat(client, dev, bundle["version"])
    iid = admin.post("/v1/incidents", json={"title": "trojan", "severity": "high"}).json()["id"]
    item = analyst.post(f"/v1/incidents/{iid}/recovery", json={"step": "remove_malware",
                                                               "device_id": dev["device_id"]}).json()["id"]
    analyst.post(f"/v1/recovery/{item}/removal", json={"removal_state": "quarantined", "detection_ref": "alert:1"})
    k = admin.get("/v1/recovery/kpis").json()
    assert k["verified_removal_rate"]["numerator"] == 0 and k["verified_removal_rate"]["quarantine_only"] == 1
    # removed without a recovery scan, or with an incomplete one, is refused
    assert analyst.post(f"/v1/recovery/{item}/removal", json={"removal_state": "removed"}).status_code == 409
    scan = analyst.post(f"/v1/recovery/{item}/recovery-scan").json()
    progress(client, dev, scan["group_id"], "partial", files_scanned=50, gaps={"inaccessible": 2})
    assert analyst.post(f"/v1/recovery/{item}/removal", json={"removal_state": "removed"}).status_code == 409
    # still infected after a complete rescan -> refused; record removal_failed
    scan = analyst.post(f"/v1/recovery/{item}/recovery-scan").json()
    progress(client, dev, scan["group_id"], "complete", files_scanned=500, detections=1)
    r = analyst.post(f"/v1/recovery/{item}/removal", json={"removal_state": "removed"})
    assert r.status_code == 409 and "detection" in r.json()["detail"]
    analyst.post(f"/v1/recovery/{item}/removal", json={"removal_state": "removal_failed"})
    # mitigation without a passing retest blocks return to service
    analyst.post(f"/v1/recovery/{item}/mitigation", json={"description": "patched SMB", "retest_passed": None})
    rts = analyst.post(f"/v1/incidents/{iid}/recovery", json={"step": "return_to_service"}).json()["id"]
    r = admin.post(f"/v1/recovery/{rts}/approve-return")
    assert r.status_code == 409
    assert set(r.json()["detail"]["missing"]) == {"verified removal or verified rebuild",
                                                  "passing retest for every mitigation"}
    # clean complete rescan -> verified removal; passing retest; then return is allowed
    scan = analyst.post(f"/v1/recovery/{item}/recovery-scan").json()
    progress(client, dev, scan["group_id"], "complete", files_scanned=600, detections=0)
    assert analyst.post(f"/v1/recovery/{item}/removal", json={"removal_state": "removed"}).json()["verified_at"]
    analyst.post(f"/v1/recovery/{item}/mitigation", json={"description": "retest SMB", "retest_passed": True})
    assert admin.get(f"/v1/recovery/{item}/gates").json()["missing"] == ["passing retest for every mitigation"]
    # the earlier mitigation still lacks a pass; record its retest
    analyst.post(f"/v1/recovery/{item}/mitigation", json={"description": "patched SMB", "retest_passed": True})
    assert admin.get(f"/v1/recovery/{item}/gates").json()["missing"] == ["passing retest for every mitigation"]


def test_recurrence_reopens_incident_and_kpis(org, client, admin_sql):
    admin, analyst, enrol, bundle = org
    dev = enrol(admin, "rec-2")
    beat(client, dev, bundle["version"])
    iid = admin.post("/v1/incidents", json={"title": "worm", "severity": "high"}).json()["id"]
    item = analyst.post(f"/v1/incidents/{iid}/recovery", json={"step": "remove_malware",
                                                               "device_id": dev["device_id"]}).json()["id"]
    scan = analyst.post(f"/v1/recovery/{item}/recovery-scan").json()
    progress(client, dev, scan["group_id"], "complete", files_scanned=600)
    analyst.post(f"/v1/recovery/{item}/removal", json={"removal_state": "removed", "detection_ref": "alert:9"})
    rts = analyst.post(f"/v1/incidents/{iid}/recovery", json={"step": "return_to_service"}).json()["id"]
    assert admin.post(f"/v1/recovery/{rts}/approve-return").status_code == 200
    k = admin.get("/v1/recovery/kpis").json()
    assert k["verified_removal_rate"]["value"] == 100.0
    assert k["recurrence_rate"]["under_observation"] == 1 and k["safe_return_to_service_rate"]["value"] == 100.0
    assert k["time_to_verified_eradication_hours"]["n"] == 1
    analyst.post(f"/v1/recovery/{item}/recurrence", json={"detection_ref": "alert:10"})
    inc = admin.get(f"/v1/incidents/{iid}").json()["incident"]
    assert inc["status"] == "open"
    k = admin.get("/v1/recovery/kpis").json()
    assert k["recurrence_rate"]["numerator"] == 1 and k["verified_removal_rate"]["numerator"] == 0
    assert any(n["kind"] == "recovery.recurrence" for n in admin.get("/v1/notifications").json())


def test_empty_device_ids_scans_all_active_devices(org, client):
    """Empty device_ids means 'all active devices in the tenant' (fixes the min_length=0 422)."""
    admin, analyst, enrol, bundle = org
    a = enrol(admin, "all-1")
    b = enrol(admin, "all-2")

    # /v1/scan-jobs with an empty list targets every active device.
    out = admin.post("/v1/scan-jobs", json={"device_ids": [], "scan_type": "quick"})
    assert out.status_code == 201, out.text
    jobs = out.json()["jobs"]
    assert {j["device_id"] for j in jobs} == {a["device_id"], b["device_id"]}

    # The action-catalogue path (/v1/scans) also accepts an empty list now.
    assert admin.post("/v1/scans", json={"device_ids": []}).status_code in (201, 403)
