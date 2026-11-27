"""INT-02/INT-03: MQTT (IoT, against a real in-process MQTT broker), SFTP (against a real in-process SSH/SFTP server),
AMQP (pika's channel contract), and outbound messaging / CRM / ITSM connectors."""
from __future__ import annotations

import asyncio
import json
import os
import socket
import threading
import time
import uuid

import httpx
import paramiko
import pytest

from app import transports
from app.routers import integrations


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _integration(admin, kind, protocol, name, **extra):
    r = admin.post("/v1/integrations", json={"name": name, "signal_kind": kind, "protocol": protocol, **extra})
    assert r.status_code == 201, r.text
    body = r.json()
    assert admin.post(f"/v1/integrations/{body['id']}/maturity",
                      json={"maturity": "test_only", "provider": "acme", "evidence": {}}).status_code == 200
    return body


def _sig(i, kind="port_scan"):
    return {"external_id": f"x-{i}", "category": kind, "severity": "medium", "observed_at": "2026-11-27T03:00:00Z"}


# ------------------------------------------------------------------ MQTT
@pytest.fixture(scope="module")
def mqtt_broker():
    from amqtt.broker import Broker
    port = _free_port()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    cfg = {"listeners": {"default": {"type": "tcp", "bind": f"127.0.0.1:{port}"}},
           "plugins": {"amqtt.plugins.authentication.AnonymousAuthPlugin": {"allow_anonymous": True}}}
    broker = Broker(cfg, loop=loop)
    threading.Thread(target=loop.run_forever, daemon=True).start()
    asyncio.run_coroutine_threadsafe(broker.start(), loop).result(10)
    yield port
    asyncio.run_coroutine_threadsafe(broker.shutdown(), loop).result(10)
    loop.call_soon_threadsafe(loop.stop)


def test_mqtt_iot_signals(new_account, mqtt_broker):
    import paho.mqtt.client as mqtt
    admin = new_account("mqtt")
    integ = _integration(admin, "firewall", "mqtt", "iot-gateway", endpoint=f"mqtt://127.0.0.1:{mqtt_broker}",
                         config={"topic": "site1/fw/#", "private_network_approved": True})

    def publish():
        time.sleep(1.0)
        p = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="sensor-1")
        p.connect("127.0.0.1", mqtt_broker)
        p.loop_start()
        p.publish("site1/fw/edge", json.dumps(_sig(1)), qos=1).wait_for_publish(5)
        p.publish("site1/fw/edge", json.dumps([_sig(2, "lateral_movement"), _sig(3)]), qos=1).wait_for_publish(5)
        p.loop_stop()
        p.disconnect()
    threading.Thread(target=publish, daemon=True).start()
    r = transports.poll_integration(uuid.UUID(integ["id"]), uuid.UUID(admin.tenant_id), check_egress=False,
                                    window_s=3.0)
    assert r["ok"] and r["ingested"] == 3, r
    bad = _integration(admin, "firewall", "mqtt", "plain-public", endpoint="mqtt://broker.example.com:1883",
                       config={"topic": "x"})
    res = transports.poll_integration(uuid.UUID(bad["id"]), uuid.UUID(admin.tenant_id), check_egress=False)
    assert res["ok"] is False and "mqtts://" in res["reason"]


# ------------------------------------------------------------------ AMQP
class _Method:
    def __init__(self, tag):
        self.delivery_tag = tag


class FakeAMQP:
    def __init__(self, bodies):
        self.queue, self.acked, self.closed = list(bodies), [], False

    def channel(self):
        return self

    def basic_get(self, queue, auto_ack):
        assert queue == "aav.signals" and auto_ack is False
        if not self.queue:
            return None, None, None
        return _Method(len(self.acked) + 1), None, self.queue.pop(0)

    def basic_ack(self, tag):
        self.acked.append(tag)

    def close(self):
        self.closed = True


def test_amqp_queue(new_account):
    admin = new_account("amqp")
    integ = _integration(admin, "firewall", "amqp", "rabbit", endpoint="amqps://mq.corp.example:5671/%2f",
                         config={"queue": "aav.signals", "username": "aav"})
    conn = FakeAMQP([json.dumps(_sig(1)).encode(), (json.dumps(_sig(2)) + "\n" + json.dumps(_sig(3))).encode()])
    r = transports.poll_integration(uuid.UUID(integ["id"]), uuid.UUID(admin.tenant_id), check_egress=False,
                                    connection_factory=lambda: conn)
    assert r["ok"] and r["ingested"] == 3 and conn.acked == [1, 2] and conn.closed, r


# ------------------------------------------------------------------ SFTP
class _Server(paramiko.ServerInterface):
    def check_auth_password(self, username, password):
        return paramiko.AUTH_SUCCESSFUL if (username, password) == ("drop", "sftp-pass") else paramiko.AUTH_FAILED

    def get_allowed_auths(self, username):
        return "password"

    def check_channel_request(self, kind, chanid):
        return paramiko.OPEN_SUCCEEDED if kind == "session" else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED


class _LocalSFTP(paramiko.SFTPServerInterface):
    ROOT = ""

    def _p(self, path):
        return os.path.join(self.ROOT, path.lstrip("/"))

    def list_folder(self, path):
        out = []
        for n in os.listdir(self._p(path)):
            a = paramiko.SFTPAttributes.from_stat(os.stat(os.path.join(self._p(path), n)))
            a.filename = n
            out.append(a)
        return out

    def stat(self, path):
        return paramiko.SFTPAttributes.from_stat(os.stat(self._p(path)))

    lstat = stat

    def open(self, path, flags, attr):
        h = paramiko.SFTPHandle(flags)
        h.readfile = open(self._p(path), "rb")
        h.filename = self._p(path)
        return h


@pytest.fixture()
def sftp_server(tmp_path):
    root = tmp_path / "sftp"
    (root / "outbox").mkdir(parents=True)
    _LocalSFTP.ROOT = str(root)
    key = paramiko.RSAKey.generate(2048)
    lsock = socket.socket()
    lsock.bind(("127.0.0.1", 0))
    lsock.listen(5)
    port = lsock.getsockname()[1]

    def serve():
        while True:
            try:
                conn, _ = lsock.accept()
            except OSError:
                return
            t = paramiko.Transport(conn)
            t.add_server_key(key)
            t.set_subsystem_handler("sftp", paramiko.SFTPServer, _LocalSFTP)
            t.start_server(server=_Server())
    threading.Thread(target=serve, daemon=True).start()
    yield port, key.get_base64(), root / "outbox"
    lsock.close()


def test_sftp_drop_folder(new_account, sftp_server):
    port, host_key, outbox = sftp_server
    (outbox / "2026-11-27-01.jsonl").write_text(json.dumps(_sig(1)) + "\n" + json.dumps(_sig(2)) + "\n")
    (outbox / "readme.txt").write_text("ignored")
    admin = new_account("sftp")
    integ = _integration(admin, "firewall", "sftp", "fw-exports", endpoint=f"sftp://127.0.0.1:{port}",
                         config={"username": "drop", "path": "/outbox", "host_key": host_key,
                                 "private_network_approved": True})
    admin.put(f"/v1/integrations/{integ['id']}/secret", json={"value": "sftp-pass"})
    iid, tid = uuid.UUID(integ["id"]), uuid.UUID(admin.tenant_id)
    r = transports.poll_integration(iid, tid, check_egress=False)
    assert r["ok"] and r["ingested"] == 2, r
    assert transports.poll_integration(iid, tid, check_egress=False)["received"] == 0      # cursor = last file
    (outbox / "2026-11-27-02.json").write_text(json.dumps([_sig(3)]))
    assert transports.poll_integration(iid, tid, check_egress=False)["ingested"] == 1
    wrong = _integration(admin, "firewall", "sftp", "fw-wrong-key", endpoint=f"sftp://127.0.0.1:{port}",
                         config={"username": "drop", "path": "/outbox", "host_key": "AAAA-not-the-key"})
    admin.put(f"/v1/integrations/{wrong['id']}/secret", json={"value": "sftp-pass"})
    res = transports.poll_integration(uuid.UUID(wrong["id"]), tid, check_egress=False)
    assert res["ok"] is False and "host key" in res["reason"]


# ------------------------------------------------------------------ outbound connectors
class Outbound:
    def __init__(self):
        self.calls = []

    def __call__(self, req: httpx.Request):
        self.calls.append(req)
        h = req.url.host
        if h == "hooks.slack.com":
            assert "Agentic Antivirus" in json.loads(req.content)["text"]
            return httpx.Response(200, text="ok")
        if h == "api.hubapi.com":
            assert req.headers["authorization"] == "Bearer hs-token"
            if req.method == "GET":
                return httpx.Response(200, json={"results": []})
            p = json.loads(req.content)["properties"]
            assert p["subject"].startswith("[Agentic Antivirus]") and p["hs_ticket_priority"] in ("HIGH", "MEDIUM", "LOW")
            return httpx.Response(201, json={"id": "9001"})
        if h == "corp.service-now.com":
            if req.method == "GET":
                return httpx.Response(200, json={"result": []})
            b = json.loads(req.content)
            assert b["short_description"].startswith("[Agentic Antivirus]") and b["urgency"] in ("1", "2", "3")
            return httpx.Response(201, json={"result": {"number": "INC0010001", "sys_id": "abc"}})
        return httpx.Response(599)


def test_outbound_messaging_crm_itsm(new_account, monkeypatch):
    fake = Outbound()
    monkeypatch.setattr(integrations, "TEST_TRANSPORT", httpx.MockTransport(fake))
    admin = new_account("outbound")
    setups = [("messaging", "slack", {}, "https://hooks.slack.com/services/T0/B0/xyz"),
              ("crm", "hubspot", {}, "hs-token"),
              ("itsm", "servicenow", {"instance": "corp"}, "aav:snow-pass")]
    for kind, prov, cfg, secret in setups:
        i = admin.post("/v1/integrations", json={"name": prov, "signal_kind": kind, "protocol": "rest",
                                                 "config": {**cfg, "provider": prov}}).json()
        assert admin.put(f"/v1/integrations/{i['id']}/secret", json={"value": secret}).status_code == 204
        assert admin.post(f"/v1/integrations/{i['id']}/verify-credentials").json()["ok"] is True
        assert admin.post(f"/v1/integrations/{i['id']}/maturity", json={
            "maturity": "verified_live", "provider": prov,
            "evidence": {"sandbox_contract_passed": True, "policy_reviewed": True}}).status_code == 200
    out = integrations.deliver_outbound(uuid.UUID(admin.tenant_id), "ddos.critical", "Critical ddos alert",
                                        {"severity": "critical", "asset": "shop.example.com"})
    assert sorted(o.get("provider") for o in out) == ["hubspot", "servicenow", "slack"]
    assert all(o["ok"] for o in out)
    assert next(o for o in out if o["provider"] == "servicenow")["number"] == "INC0010001"
    with pytest.raises(Exception, match="webhook URL"):
        from app.providers.outbound import Slack
        Slack({}, "https://evil.example/hook", check_egress=False)
