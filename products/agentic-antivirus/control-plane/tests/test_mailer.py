"""Outbound mail: queued verification mail is delivered over SMTP, and the operator CLI can verify."""
import dataclasses
import uuid

import pytest

from app import admin, mailer


class FakeSMTP:
    def __init__(self, fail_for=()):
        self.sent, self.fail_for = [], set(fail_for)

    def send_message(self, msg):
        if msg["To"] in self.fail_for:
            raise OSError("mailbox unavailable")
        self.sent.append(msg)

    def quit(self):
        pass


@pytest.fixture
def smtp(monkeypatch, admin_sql):
    # Other tests leave mail queued; set it aside so each pass here only sees this test's mail.
    admin_sql("UPDATE aav.outbound_mail SET status = 'sent' WHERE status = 'queued'")
    fake = FakeSMTP()
    monkeypatch.setattr(mailer, "settings", dataclasses.replace(
        mailer.settings, smtp_host="smtp.example.test", mail_from="no-reply@example.test", mail_daily_cap=10_000))
    monkeypatch.setenv("AAV_SMTP_PASSWORD", "test-only")
    monkeypatch.setattr(mailer, "_connect", lambda: fake)
    return fake


def _register(client, email):
    r = client.post("/v1/auth/register", json={"email": email, "password": "a sufficiently long pw",
                                               "organisation": "Mail Org"})
    assert r.status_code == 201, r.text
    return r.json()


def test_delivery_off_without_config(client, admin_sql):
    assert mailer.configured() is False
    assert mailer.deliver_pending() == {"configured": False, "sent": 0, "failed": 0}
    r = _register(client, f"off-{uuid.uuid4().hex[:8]}@example.com")
    assert r["email_verification"] == "delivery_not_configured"


def test_verification_mail_is_sent_and_link_verifies(client, admin_sql, smtp):
    email = f"mail-{uuid.uuid4().hex[:8]}@example.com"
    _register(client, email)
    mailer.deliver_pending()
    mine = [m for m in smtp.sent if m["To"] == email]
    assert len(mine) == 1 and mine[0]["Subject"].startswith("Confirm your email")
    text = mine[0].get_body(("plain",)).get_content()
    assert "/verify-email?token=" in text
    token = text.split("token=")[1].split()[0]
    assert client.post("/v1/auth/verify-email", json={"token": token}).status_code == 200
    row = admin_sql("SELECT status, payload FROM aav.outbound_mail WHERE to_email = %s", email)[0]
    assert row["status"] == "sent" and "sent_at" in row["payload"]


def test_failures_retry_then_fail(client, admin_sql, smtp):
    email = f"bounce-{uuid.uuid4().hex[:8]}@example.com"
    _register(client, email)
    smtp.fail_for.add(email)
    for _ in range(mailer.MAX_ATTEMPTS):
        mailer.deliver_pending()
    row = admin_sql("SELECT status, payload FROM aav.outbound_mail WHERE to_email = %s", email)[0]
    assert row["status"] == "failed" and row["payload"]["attempts"] == mailer.MAX_ATTEMPTS
    assert "token" not in row["payload"]["last_error"]


def test_daily_cap_is_respected(client, admin_sql, smtp, monkeypatch):
    monkeypatch.setattr(mailer, "settings", dataclasses.replace(mailer.settings, mail_daily_cap=0))
    _register(client, f"cap-{uuid.uuid4().hex[:8]}@example.com")
    assert mailer.deliver_pending().get("capped") is True


def test_resend_is_rate_limited(client, admin_sql):
    email = f"resend-{uuid.uuid4().hex[:8]}@example.com"
    _register(client, email)
    for _ in range(3):
        assert client.post("/v1/auth/resend-verification", json={"email": email}).status_code == 200
    n = admin_sql("SELECT count(*) AS n FROM aav.outbound_mail WHERE to_email = %s", email)[0]["n"]
    assert n == 1


def test_operator_cli_verifies_and_audits(client, admin_sql):
    email = f"cli-{uuid.uuid4().hex[:8]}@example.com"
    body = _register(client, email)
    tok = client.post("/v1/auth/login", json={"email": email, "password": "a sufficiently long pw"}).json()
    h = {"Authorization": f"Bearer {tok['access_token']}", "X-Tenant-Id": body["tenant_id"]}
    assert client.get("/v1/devices", headers=h).status_code == 403
    assert admin.main(["verify-email", email.upper()]) == 0
    assert client.get("/v1/devices", headers=h).status_code == 200
    assert admin.main(["verify-email", "nobody@example.com"]) == 1
    audit = admin_sql("SELECT actor FROM aav.audit_log WHERE action = 'account.email_verified_by_operator' "
                      "AND target = %s", body["user_id"])
    assert audit and audit[0]["actor"] == "operator:cli"



def test_publish_baseline_is_idempotent(admin_sql, tmp_path):
    import json
    from app import admin as adm
    revoked = admin_sql("UPDATE aav.update_bundles SET revoked_at = now() WHERE kind = 'detections' "
                        "AND revoked_at IS NULL RETURNING id")
    try:
        doc = json.loads(adm.BASELINE.read_text())
        doc["version"] = f"test-{uuid.uuid4().hex[:8]}"
        f = tmp_path / "baseline.json"
        f.write_text(json.dumps(doc))
        assert adm.publish_baseline(f) == 0
        active = "SELECT version FROM aav.update_bundles WHERE kind = 'detections' AND revoked_at IS NULL"
        assert [r["version"] for r in admin_sql(active)] == [doc["version"]]
        assert adm.publish_baseline(f) == 0          # already published: no second bundle
        assert len(admin_sql(active)) == 1
    finally:
        admin_sql("UPDATE aav.update_bundles SET revoked_at = now() WHERE version LIKE 'test-%%'")
        for r in revoked:
            admin_sql("UPDATE aav.update_bundles SET revoked_at = NULL WHERE id = %s", r["id"])


def test_ip_relay_needs_no_password(monkeypatch):
    monkeypatch.delenv("AAV_SMTP_PASSWORD", raising=False)
    monkeypatch.setattr(mailer, "settings", dataclasses.replace(
        mailer.settings, smtp_host="smtp-relay.gmail.com", mail_from="admin@example.test", smtp_user=""))
    assert mailer.configured() is True
    monkeypatch.setattr(mailer, "settings", dataclasses.replace(mailer.settings, smtp_user="admin@example.test"))
    assert mailer.configured() is False
