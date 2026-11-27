"""SEC-01, SEC-02, REC-01, DDOS-01..05, DDL-01..04, THR-00..10, INT-*, AX-09, FN-07."""
from datetime import datetime, timezone

import pytest


@pytest.fixture
def org(new_account, invite, enrol):
    admin = new_account("thr")
    analyst = invite(admin, "security_analyst")
    dev = enrol(admin, "web-01", "linux")
    return admin, analyst, dev


def _integration(admin, kind, protocol="webhook", maturity="test_only"):
    r = admin.post("/v1/integrations", json={"name": f"{kind}-1", "signal_kind": kind, "protocol": protocol})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["maturity"] == "unavailable" and body["enabled"] is False
    if maturity:
        assert admin.post(f"/v1/integrations/{body['id']}/maturity",
                          json={"maturity": maturity, "provider": "acme", "evidence": {}}).status_code == 200
    return body


def _ingest(client, integ, **kw):
    payload = {"external_id": kw.pop("external_id", "x1"), "category": kw.pop("category"),
               "severity": kw.pop("severity", "high"), "observed_at": datetime.now(timezone.utc).isoformat(), **kw}
    return client.post(f"/v1/ingest/{integ['id']}", headers={"X-AAV-Webhook-Secret": integ["webhook_secret"]},
                       json=payload)


def test_unavailable_integration_rejects_data_and_cannot_be_promoted_to_live(org, client):
    admin, analyst, dev = org
    integ = _integration(admin, "identity", maturity=None)
    assert _ingest(client, integ, category="unusual_sign_in").status_code == 409
    r = admin.post(f"/v1/integrations/{integ['id']}/maturity", json={"maturity": "verified_live", "provider": "acme",
                   "evidence": {"sandbox_contract_passed": True, "credential_verified": True, "policy_reviewed": True}})
    assert r.status_code == 409  # no verified adapter exists
    assert _ingest(client, dict(integ, webhook_secret="wrong"), category="unusual_sign_in").status_code == 401
    assert admin.post("/v1/integrations", json={"name": "bad", "signal_kind": "dns", "protocol": "rest",
                                                "config": {"password": "x"}}).status_code == 422


def test_identity_alert_attributed_and_account_action_needs_scoped_approval(org, client):
    admin, analyst, dev = org
    integ = _integration(admin, "identity")
    r = _ingest(client, integ, category="repeated_failures", severity="high", device_hostname="web-01",
                user_ref="alice@example.com")
    body = r.json()
    assert body["device_id"] == dev["device_id"] and body["simulation"] is True and body["incident_id"]
    tl = admin.get(f"/v1/incidents/{body['incident_id']}").json()["timeline"]
    assert tl[0]["type"] == "external_alert" and tl[0]["data"]["simulation"] is True
    assert _ingest(client, integ, category="repeated_failures").json() == {"duplicate": True}
    assert _ingest(client, integ, external_id="x2", category="volumetric_flood").status_code == 422
    r = analyst.post("/v1/actions", json={"action_type": "suspend_account", "targets": ["alice@example.com"],
                                          "params": {"integration_id": integ["id"]}, "incident_id": body["incident_id"]})
    rid = r.json()["id"]
    assert r.json()["status"] == "proposed"
    analyst.post(f"/v1/actions/{rid}/approve", json={})
    out = analyst.post(f"/v1/actions/{rid}/dispatch").json()
    assert out["status"] == "failed" and "no verified_live identity adapter" in out["commands"][0]["reason"]


def test_phishing_report_linked_and_escalated(org, client):
    admin, analyst, dev = org
    user = analyst
    client.post("/v1/agent/events", headers={"X-Device-Key": dev["device_key"]}, json={"events": [
        {"event_uid": "u1", "kind": "url_visit", "occurred_at": "2026-11-18T09:00:00+00:00",
         "data": {"url": "https://login.example-bad.test/", "process": "chrome"}}]})
    r = user.post("/v1/reports", json={"kind": "email", "description": "fake invoice email",
                                       "url": "https://login.example-bad.test/", "device_id": dev["device_id"]})
    assert r.status_code == 201 and r.json()["incident_id"] and r.json()["linked_event_ids"]
    assert any(n["kind"] == "report.escalated" for n in admin.get("/v1/notifications").json())


def test_url_reputation_engine():
    from aav_detection import Engine
    e = Engine({"reputation": {"malicious_domains": ["evil.test"], "malicious_urls": []}}, "t")
    assert e.check_url("https://a.evil.test/x").rule_id == "reputation.url"
    assert e.check_url("https://notevil.test/") is None


def test_ddos_asset_coverage_and_uncovered_alert(org):
    admin, analyst, dev = org
    admin.post("/v1/assets", json={"kind": "hostname", "value": "shop.example.com", "service": "shop",
                                   "service_owner": "web team", "provider": "upstream-x", "mitigation_policy": "always-on",
                                   "capacity_assumptions": "10 Gbps clean"})
    r = admin.post("/v1/assets", json={"kind": "ip", "value": "93.184.216.34", "service": "api"})
    assert r.json()["covered"] is False
    assert any(n["kind"] == "ddos.uncovered_asset" for n in admin.get("/v1/notifications").json())
    cov = admin.get("/v1/ddos/coverage").json()
    assert cov["public_endpoints"] == 2 and cov["accounted_for"] == 1 and cov["accounted_pct"] == 50.0
    admin.post("/v1/assets", json={"kind": "ip", "value": "93.184.216.34", "service": "api",
                                   "exception_note": "internal-only, not internet reachable"})
    assert admin.get("/v1/ddos/coverage").json()["uncovered"] == []


def test_critical_provider_alert_notifies_within_60s_and_tracks_mitigation(org, client):
    admin, analyst, dev = org
    admin.post("/v1/assets", json={"kind": "hostname", "value": "shop.example.com", "service": "shop",
                                   "provider": "upstream-x", "mitigation_policy": "always-on"})
    ddos = _integration(admin, "ddos")
    r = _ingest(client, ddos, category="volumetric_flood", severity="critical", asset="shop.example.com",
                confirmed=False, data={"gbps": 40})
    assert r.json()["incident_id"]
    _ingest(client, ddos, external_id="m1", category="mitigation_started", severity="critical",
            asset="shop.example.com", confirmed=True)
    st = admin.get("/v1/ddos/status").json()
    assert st["mitigation_active"][0]["value"] == "shop.example.com"
    assert "shop.example.com" in st["affected_assets"]
    k = admin.get("/v1/kpis").json()["provider_alert_notification_seconds"]
    assert k["n"] >= 2 and k["within_60s_ratio"] == 1.0
    lb = _integration(admin, "load_balancer")
    _ingest(client, lb, external_id="lb1", category="connection_saturation", severity="high", asset="shop.example.com")
    iid = r.json()["incident_id"]
    f = analyst.post(f"/v1/incidents/{iid}/investigate", json={}).json()["findings"]
    assert f["impact"]["suspected"] == [] or "shop.example.com" in f["impact"]["suspected"] + f["impact"]["confirmed"]
    assert "shop.example.com" in f["impact"]["confirmed"]  # mitigation_started was confirmed=True
    assert f["priorities"][0] == "shop.example.com"


def test_traffic_policy_approval_and_honest_execution(org):
    admin, analyst, dev = org
    admin.post("/v1/service-objectives", json={"service": "shop", "availability_pct": 99.9, "latency_p95_ms": 400,
                                               "success_rate_pct": 99.5})
    assert admin.get("/v1/service-objectives").json()[0]["latency_p95_ms"] == 400
    r = analyst.post("/v1/traffic-policies", json={"service": "shop", "control": "rate_limit",
                                                   "config": {"rps_per_ip": 50}, "reason": "L7 flood"})
    tp, act = r.json()["traffic_policy_id"], r.json()["action"]
    assert act["status"] == "proposed"
    assert analyst.post(f"/v1/actions/{act['id']}/approve", json={}).status_code == 403  # tenant admin only
    assert admin.post(f"/v1/actions/{act['id']}/approve", json={}).status_code == 200
    out = admin.post(f"/v1/actions/{act['id']}/dispatch").json()
    assert out["status"] == "failed" and "not applied" in out["commands"][0]["reason"]
    assert next(t for t in admin.get("/v1/traffic-policies").json() if t["id"] == tp)["status"] == "approved"
    rb = analyst.post(f"/v1/traffic-policies/{tp}/rollback").json()
    assert rb["status"] == "proposed"


def test_recovery_backup_and_return_to_service(org, client):
    admin, analyst, dev = org
    iid = admin.post("/v1/incidents", json={"title": "ransomware", "severity": "critical"}).json()["id"]
    step = analyst.post(f"/v1/incidents/{iid}/recovery", json={"step": "restore_from_backup",
                                                               "device_id": dev["device_id"]}).json()["id"]
    backup = _integration(admin, "backup")
    ev = analyst.post(f"/v1/recovery/{step}/verify-backup", json={"integration_id": backup["id"]}).json()
    assert ev["verified"] is None and "unknown" in ev["reason"]
    analyst.patch(f"/v1/recovery/{step}", json={"status": "done", "restore_outcome": {"files": 120, "ok": True}})
    rts = analyst.post(f"/v1/incidents/{iid}/recovery", json={"step": "return_to_service"}).json()["id"]
    assert admin.patch(f"/v1/incidents/{iid}", json={"status": "resolved"}).status_code == 409
    assert analyst.post(f"/v1/recovery/{rts}/approve-return").status_code == 403
    assert admin.post(f"/v1/recovery/{rts}/approve-return").status_code == 200
    assert admin.patch(f"/v1/incidents/{iid}", json={"status": "resolved"}).status_code == 200


def test_egress_policy_blocks_ssrf(org):
    admin, analyst, dev = org
    from app.netpolicy import EgressDenied, check_endpoint
    fake = lambda host, port, proto=0: [(2, 1, 6, "", ("10.0.0.5", port))]  # noqa: E731
    with pytest.raises(EgressDenied):
        check_endpoint("http://api.example.com/", resolver=fake)  # plaintext
    with pytest.raises(EgressDenied):
        check_endpoint("https://evil.test/", resolver=fake)  # not allowlisted
    with pytest.raises(EgressDenied):
        check_endpoint("https://api.example.com/", resolver=fake)  # private address
    ok = check_endpoint("https://api.example.com/", resolver=lambda h, p, proto=0: [(2, 1, 6, "", ("93.184.215.14", p))])
    assert ok["addresses"] == ["93.184.215.14"]
    i = admin.post("/v1/integrations", json={"name": "meta", "signal_kind": "cloud_audit", "protocol": "rest",
                                             "endpoint": "https://169.254.169.254/latest"}).json()
    h = admin.post(f"/v1/integrations/{i['id']}/health").json()
    assert h["ok"] is False


def test_coverage_records_per_layer(org, client):
    admin, analyst, dev = org
    _integration(admin, "dns")
    cov = {c["layer"]: c for c in admin.get("/v1/coverage").json()}
    assert cov["endpoint"]["supported_assets"] == [{"os": "linux", "devices": 1}]
    assert "no enrolled windows devices" in cov["endpoint"]["gaps"]
    assert any("test_only" in g for g in cov["network"]["gaps"])
    assert "no enabled identity integration" in cov["identity"]["gaps"]


def test_rotate_webhook_secret_revokes_the_old_one(org, client, new_account, admin_sql):
    admin, analyst, dev = org
    integ = _integration(admin, "identity")
    assert _ingest(client, integ, category="unusual_sign_in", external_id="rot-1").status_code == 202
    old = integ["webhook_secret"]

    assert analyst.post(f"/v1/integrations/{integ['id']}/rotate-webhook-secret").status_code == 403
    other = new_account("rotate-other-tenant")
    assert other.post(f"/v1/integrations/{integ['id']}/rotate-webhook-secret").status_code == 404

    r = admin.post(f"/v1/integrations/{integ['id']}/rotate-webhook-secret")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["webhook_url"] == f"/v1/ingest/{integ['id']}" and body["webhook_secret"] != old

    assert _ingest(client, integ, category="unusual_sign_in", external_id="rot-2").status_code == 401   # old secret dead
    fresh = dict(integ, webhook_secret=body["webhook_secret"])
    assert _ingest(client, fresh, category="unusual_sign_in", external_id="rot-3").status_code == 202

    rows = admin_sql("SELECT actor, detail::text AS detail FROM aav.audit_log WHERE action = "
                     "'integration.webhook_secret_rotated' AND target = %s", integ["id"])
    assert len(rows) == 1 and body["webhook_secret"] not in rows[0]["detail"]          # audited, secret not logged
    hashes = admin_sql("SELECT webhook_secret_hash FROM aav.integrations WHERE id = %s", integ["id"])
    assert body["webhook_secret"] not in hashes[0]["webhook_secret_hash"]                # only the hash is stored
