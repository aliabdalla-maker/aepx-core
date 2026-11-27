"""Signal transports beyond REST webhooks (INT-02). All of them end in integrations.ingest_signal, so validation,
deduplication, device attribution, incident linking, notification and audit are identical to the webhook path.

Push:
- gRPC: service aav.ingest.v1.Ingest, method Submit, request and response google.protobuf.Struct (no code generation
  needed by clients). Metadata: x-aav-integration-id, x-aav-webhook-secret. Started when AAV_GRPC_PORT is set;
  plaintext on loopback only — publish it through the TLS reverse proxy (h2c upstream) like the console.
Pull (python -m app.admin poll-integrations, or every AAV_POLL_SECONDS in the control plane):
- SQL: protocol "sql", endpoint postgresql://user@host:5432/db, credential = password. config.query is one SELECT
  returning the canonical columns (external_id, category, severity, observed_at, and optionally asset,
  device_hostname, device_ip, user_ref, confirmed, data) with a %(cursor)s parameter; config.cursor_column (default
  external_id) advances the cursor. Runs in a READ ONLY transaction with a statement timeout.
- MQTT (IoT), AMQP and SFTP: see poll_mqtt, poll_amqp, poll_sftp below.
- IMAP: protocol "imap" on an email integration, endpoint imaps://host:993, config.username, config.mailbox
  (default INBOX), credential = password. Each unseen message becomes a phishing_report (malicious_url when a URL
  in it is on the detection bundle's reputation list); the message is then marked seen.
"""
from __future__ import annotations

import email
import email.policy
import email.utils
import imaplib
import json
import logging
import re
import threading
from concurrent import futures
from datetime import datetime, timezone
from urllib.parse import urlparse
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError

from app import db, netpolicy
from app.routers import integrations as integ_mod

log = logging.getLogger("aav.transports")
GRPC_METHOD = "/aav.ingest.v1.Ingest/Submit"
URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.I)
MAX_POLL_ROWS = 500


# ----------------------------------------------------------------------------- gRPC
def _grpc_submit(request, context):
    from google.protobuf import json_format, struct_pb2
    import grpc
    md = dict(context.invocation_metadata())
    try:
        iid = UUID(md.get("x-aav-integration-id", ""))
        integ = integ_mod.authenticate_ingest(iid, md.get("x-aav-webhook-secret"))
        body = integ_mod.IngestIn(**json_format.MessageToDict(request))
        out = integ_mod.ingest_signal(iid, integ, body)
    except ValueError as exc:                      # bad UUID or pydantic validation
        context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc)[:300])
    except HTTPException as exc:
        code = {401: grpc.StatusCode.UNAUTHENTICATED, 409: grpc.StatusCode.FAILED_PRECONDITION,
                422: grpc.StatusCode.INVALID_ARGUMENT}.get(exc.status_code, grpc.StatusCode.INTERNAL)
        context.abort(code, str(exc.detail))
    resp = struct_pb2.Struct()
    resp.update(json.loads(json.dumps(out, default=str)))
    return resp


def start_grpc(port: int, host: str = "127.0.0.1"):
    import grpc
    from google.protobuf import struct_pb2
    handler = grpc.method_handlers_generic_handler("aav.ingest.v1.Ingest", {
        "Submit": grpc.unary_unary_rpc_method_handler(
            _grpc_submit, request_deserializer=struct_pb2.Struct.FromString,
            response_serializer=struct_pb2.Struct.SerializeToString)})
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8), handlers=[handler],
                         options=[("grpc.max_receive_message_length", 1 << 20)])
    bound = server.add_insecure_port(f"{host}:{port}")
    server.start()
    return server, bound


# ----------------------------------------------------------------------------- pull transports
def _load(cur, iid) -> tuple[dict, str]:
    cur.execute("SELECT * FROM aav.integrations WHERE id = %s", (iid,))
    integ = cur.fetchone()
    cur.execute("SELECT nonce, ciphertext FROM aav.integration_secrets WHERE integration_id = %s", (iid,))
    s = cur.fetchone()
    from app import crypto
    secret = crypto.open_secret(bytes(s["nonce"]), bytes(s["ciphertext"]), f"{integ['tenant_id']}:{iid}") if s else ""
    return integ, secret


def _save_cursor(tid, iid, cursor, result: dict) -> None:
    with db.tenant_tx(tid) as cur:
        cur.execute("UPDATE aav.integrations SET config = config || %s, last_health = %s WHERE id = %s",
                    (json.dumps({"poll_cursor": cursor} if cursor is not None else {}), json.dumps(result), iid))


def poll_sql(integ: dict, secret: str, *, check_egress: bool = True) -> tuple[list[dict], object]:
    import psycopg
    from psycopg.rows import dict_row
    cfg = integ["config"]
    query = (cfg.get("query") or "").strip()
    if not re.match(r"(?is)^select\s", query) or ";" in query.rstrip(";"):
        raise ValueError("config.query must be a single SELECT statement")
    if check_egress:
        netpolicy.check_endpoint(integ["endpoint"], allow_private=bool(cfg.get("private_network_approved")))
    info = psycopg.conninfo.conninfo_to_dict(integ["endpoint"])
    if secret:
        info["password"] = secret
    cursor_col = cfg.get("cursor_column", "external_id")
    with psycopg.connect(**info, connect_timeout=10, row_factory=dict_row) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = '15s'")
            cur.execute(f"SELECT * FROM ({query.rstrip(';')}) q LIMIT {MAX_POLL_ROWS}",
                        {"cursor": cfg.get("poll_cursor", cfg.get("initial_cursor", ""))})
            rows = cur.fetchall()
    last = rows[-1][cursor_col] if rows and cursor_col in rows[-1] else cfg.get("poll_cursor")
    return rows, (str(last) if last is not None else None)


def poll_imap(integ: dict, secret: str, *, check_egress: bool = True, imap_factory=None) -> tuple[list[dict], None]:
    cfg = integ["config"]
    u = urlparse(integ["endpoint"])
    if check_egress:
        netpolicy.check_endpoint(integ["endpoint"], allow_private=bool(cfg.get("private_network_approved")))
    if imap_factory is None:
        if u.scheme != "imaps":
            raise ValueError("IMAP must use imaps:// (TLS)")
        imap_factory = lambda: imaplib.IMAP4_SSL(u.hostname, u.port or 993, timeout=20)  # noqa: E731
    from app.detections import current_engine
    eng = current_engine()
    out = []
    m = imap_factory()
    try:
        m.login(cfg["username"], secret)
        m.select(cfg.get("mailbox", "INBOX"))
        typ, data = m.uid("SEARCH", None, "UNSEEN")
        for uid in (data[0] or b"").split()[:MAX_POLL_ROWS]:
            typ, msgdata = m.uid("FETCH", uid, "(BODY.PEEK[])")
            raw = next((p[1] for p in msgdata if isinstance(p, tuple)), b"")
            msg = email.message_from_bytes(raw, policy=email.policy.default)
            text = ""
            for part in msg.walk():
                if part.get_content_type() in ("text/plain", "text/html"):
                    try:
                        text += part.get_content()
                    except (LookupError, ValueError):
                        pass
            urls = sorted(set(URL_RE.findall(text)))[:50]
            bad = [x for x in urls if eng and eng.check_url(x)]
            out.append({"external_id": (msg.get("Message-ID") or f"imap-uid-{uid.decode()}").strip()[:200],
                        "category": "malicious_url" if bad else "phishing_report",
                        "severity": "high" if bad else "medium",
                        "observed_at": (msg.get("Date") and email.utils.parsedate_to_datetime(msg["Date"]))
                        or datetime.now(timezone.utc),
                        "user_ref": email.utils.parseaddr(msg.get("From", ""))[1][:320] or None,
                        "data": {"subject": str(msg.get("Subject", ""))[:300], "urls": urls, "malicious_urls": bad,
                                 "transport": "imap"}})
            m.uid("STORE", uid, "+FLAGS", "(\\Seen)")
    finally:
        try:
            m.logout()
        except Exception:
            pass
    return out, None


def _signals(raw: bytes) -> list[dict]:
    """A message or file holds one JSON signal, a JSON array of signals, or JSON lines."""
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return []
    try:
        v = json.loads(text)
        return v if isinstance(v, list) else [v]
    except ValueError:
        return [json.loads(line) for line in text.splitlines() if line.strip()]


def poll_mqtt(integ: dict, secret: str, *, check_egress: bool = True, window_s: float = 5.0,
              client_factory=None) -> tuple[list[dict], None]:
    """IoT / MQTT: persistent session (clean_session off, QoS 1, client id per integration), so the broker keeps
    messages between polls; collects for window_s seconds. Endpoint mqtts://host:8883 (mqtt:// only when
    config.private_network_approved). Each message: one JSON signal, an array, or JSON lines."""
    import time
    import paho.mqtt.client as mqtt
    cfg = integ["config"]
    u = urlparse(integ["endpoint"])
    if u.scheme not in ("mqtts", "mqtt") or (u.scheme == "mqtt" and not cfg.get("private_network_approved")):
        raise ValueError("MQTT must use mqtts:// (TLS) unless the endpoint is an approved private network")
    if check_egress:
        netpolicy.check_endpoint(integ["endpoint"].replace("mqtt://", "mqtts://"),
                                 allow_private=bool(cfg.get("private_network_approved")))
    got: list[dict] = []
    c = (client_factory or mqtt.Client)(mqtt.CallbackAPIVersion.VERSION2, client_id=f"aav-{integ['id']}",
                                         clean_session=False)
    if cfg.get("username"):
        c.username_pw_set(cfg["username"], secret or None)
    if u.scheme == "mqtts":
        c.tls_set()
    c.on_message = lambda _c, _u, m: got.extend(_signals(m.payload))
    c.on_connect = lambda cl, _u, _f, rc, _p=None: cl.subscribe(cfg.get("topic", "aav/signals/#"), qos=1)
    c.connect(u.hostname, u.port or (8883 if u.scheme == "mqtts" else 1883), keepalive=30)
    c.loop_start()
    try:
        time.sleep(window_s)
    finally:
        c.loop_stop()
        c.disconnect()
    return got[:MAX_POLL_ROWS], None


def poll_amqp(integ: dict, secret: str, *, check_egress: bool = True, connection_factory=None) -> tuple[list[dict], None]:
    """AMQP 0-9-1 (RabbitMQ and compatible): basic_get from config.queue until empty, ack each message after it
    has been read. Endpoint amqps://host:5671/vhost; config.username; credential = password."""
    import pika
    cfg = integ["config"]
    if check_egress:
        netpolicy.check_endpoint(integ["endpoint"], allow_private=bool(cfg.get("private_network_approved")))
    if connection_factory is None:
        params = pika.URLParameters(integ["endpoint"])
        params.credentials = pika.PlainCredentials(cfg.get("username", "guest"), secret)
        connection_factory = lambda: pika.BlockingConnection(params)  # noqa: E731
    conn = connection_factory()
    out: list[dict] = []
    try:
        ch = conn.channel()
        while len(out) < MAX_POLL_ROWS:
            method, _props, body = ch.basic_get(queue=cfg["queue"], auto_ack=False)
            if method is None:
                break
            out.extend(_signals(body))
            ch.basic_ack(method.delivery_tag)
    finally:
        conn.close()
    return out, None


def poll_sftp(integ: dict, secret: str, *, check_egress: bool = True, transport_factory=None) -> tuple[list[dict], str]:
    """SFTP drop folder: reads new *.json / *.jsonl files under config.path (sorted by name, newer than the cursor),
    each holding signals as JSON or JSON lines. Endpoint sftp://host:22; config.username, config.host_key
    (base64 of the server's public key: required, the connection is refused on mismatch); credential = password."""
    import fnmatch
    import paramiko
    cfg = integ["config"]
    u = urlparse(integ["endpoint"])
    if check_egress:
        netpolicy.check_endpoint(integ["endpoint"], allow_private=bool(cfg.get("private_network_approved")))
    if transport_factory is None:
        def transport_factory():
            t = paramiko.Transport((u.hostname, u.port or 22))
            t.connect(username=cfg["username"], password=secret)
            return t
    t = transport_factory()
    try:
        key = t.get_remote_server_key()
        if not cfg.get("host_key") or key.get_base64() != cfg["host_key"]:
            raise ValueError("SFTP host key does not match config.host_key (refusing to read)")
        sftp = paramiko.SFTPClient.from_transport(t)
        base = cfg.get("path", ".")
        cursor = cfg.get("poll_cursor", "")
        names = sorted(n for n in sftp.listdir(base)
                       if fnmatch.fnmatch(n, cfg.get("pattern", "*.json*")) and n > cursor)
        out: list[dict] = []
        last = cursor
        for n in names:
            with sftp.open(f"{base.rstrip('/')}/{n}", "rb") as f:
                out.extend(_signals(f.read(5 * 1024 * 1024)))
            last = n
            if len(out) >= MAX_POLL_ROWS:
                break
        return out, last or None
    finally:
        t.close()


def poll_integration(iid: UUID, tid: UUID, **kw) -> dict:
    with db.tenant_tx(tid) as cur:
        integ, secret = _load(cur, iid)
    now = datetime.now(timezone.utc).isoformat()
    try:
        if integ["protocol"] == "sql":
            rows, cursor = poll_sql(integ, secret, **{k: v for k, v in kw.items() if k == "check_egress"})
        elif integ["protocol"] == "imap":
            rows, cursor = poll_imap(integ, secret, **kw)
        elif integ["protocol"] == "mqtt":
            rows, cursor = poll_mqtt(integ, secret, **kw)
        elif integ["protocol"] == "amqp":
            rows, cursor = poll_amqp(integ, secret, **kw)
        elif integ["protocol"] == "sftp":
            rows, cursor = poll_sftp(integ, secret, **kw)
        else:
            raise ValueError(f"protocol {integ['protocol']} is not pulled")
    except Exception as exc:                        # unreachable source, bad query, auth failure
        result = {"ok": False, "reason": f"{type(exc).__name__}: {exc}"[:300], "checked_at": now}
        _save_cursor(tid, iid, None, result)
        return result
    stats = {"received": len(rows), "ingested": 0, "duplicates": 0, "rejected": 0}
    for r in rows:
        try:
            body = integ_mod.IngestIn(**{k: r[k] for k in r if k in integ_mod.IngestIn.model_fields})
            res = integ_mod.ingest_signal(iid, integ, body)
            stats["duplicates" if res.get("duplicate") else "ingested"] += 1
        except (ValidationError, HTTPException, ValueError):
            stats["rejected"] += 1
    result = {"ok": True, **stats, "checked_at": now}
    _save_cursor(tid, iid, cursor, result)
    return result


def poll_all(**kw) -> list[dict]:
    with db.global_tx() as cur:
        cur.execute("SELECT * FROM aav.pollable_integrations()")
        targets = cur.fetchall()
    return [{"integration_id": str(t["id"]), **poll_integration(t["id"], t["tenant_id"], **kw)} for t in targets]


def start_poller(interval_s: int) -> threading.Event:
    stop = threading.Event()

    def loop():
        while not stop.wait(interval_s):
            try:
                poll_all()
            except Exception:  # pragma: no cover - logged and retried next interval
                log.exception("integration poll failed")
    threading.Thread(target=loop, name="aav-integration-poller", daemon=True).start()
    return stop
