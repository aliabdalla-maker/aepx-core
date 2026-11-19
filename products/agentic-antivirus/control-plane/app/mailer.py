"""Outbound mail worker: delivers rows from aav.outbound_mail over SMTP (STARTTLS or implicit TLS).

Rows are claimed with FOR UPDATE SKIP LOCKED, so several API workers can run this safely. A row is
marked 'sent' only after the SMTP server accepts it; after MAX_ATTEMPTS failures it is marked 'failed'.
Links carry single-use tokens, so they are never logged. Delivery is off until AAV_SMTP_HOST,
AAV_MAIL_FROM and the password are configured; queued mail is then sent on the first pass.
"""
from __future__ import annotations

import html
import json
import logging
import os
import smtplib
import ssl
import threading
from email.message import EmailMessage

from app import db
from app.config import settings

log = logging.getLogger("aav.mailer")
MAX_ATTEMPTS = 5
BATCH = 10

TEMPLATES = {
    "verify-email": ("Confirm your email for Agentic Antivirus",
                     "Confirm your email address to finish setting up your Agentic Antivirus account.",
                     "Confirm email", "This link works once and expires in 48 hours."),
    "reset-password": ("Reset your Agentic Antivirus password",
                       "Someone asked to reset the password for this Agentic Antivirus account.",
                       "Choose a new password",
                       "This link works once and expires in 1 hour. If you did not ask for this, ignore this email."),
    "accept-invite": ("You have been invited to Agentic Antivirus",
                      "You have been invited to join an organisation on Agentic Antivirus.",
                      "Accept invitation", "This link works once and expires in 72 hours."),
}


def _password() -> str:
    path = settings.smtp_password_file
    if path:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    return os.getenv("AAV_SMTP_PASSWORD", "")


def configured() -> bool:
    return bool(settings.smtp_host and settings.mail_from and (settings.smtp_password_file
                                                              or os.getenv("AAV_SMTP_PASSWORD")))


def render(to: str, template: str, payload: dict) -> EmailMessage:
    subject, intro, action, note = TEMPLATES[template]
    link = payload["link"]
    href = html.escape(link, quote=True)
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.mail_from
    msg["To"] = to
    msg.set_content(f"{intro}\n\n{action}: {link}\n\n{note}\n\nAgentic Antivirus, Software Equality\n")
    msg.add_alternative(
        f"<p>{intro}</p><p><a href=\"{href}\">{action}</a></p><p style=\"color:#555\">{note}</p>"
        "<p style=\"color:#555\">Agentic Antivirus, Software Equality</p>", subtype="html")
    return msg


def _connect() -> smtplib.SMTP:
    ctx = ssl.create_default_context()
    if settings.smtp_port == 465:
        smtp: smtplib.SMTP = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20, context=ctx)
    else:
        smtp = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20)
        smtp.starttls(context=ctx)
    if settings.smtp_user:
        smtp.login(settings.smtp_user, _password())
    return smtp


def deliver_pending() -> dict:
    """One delivery pass. Returns counts; safe to call from tests or an operator shell."""
    if not configured():
        return {"configured": False, "sent": 0, "failed": 0}
    sent = failed = 0
    with db.global_tx() as cur:
        cur.execute("SELECT count(*) AS n FROM aav.outbound_mail WHERE status = 'sent' "
                    "AND (payload->>'sent_at')::timestamptz > now() - interval '1 day'")
        room = settings.mail_daily_cap - cur.fetchone()["n"]
        if room <= 0:
            return {"configured": True, "sent": 0, "failed": 0, "capped": True}
        cur.execute("SELECT id, to_email, template, payload FROM aav.outbound_mail WHERE status = 'queued' "
                    "ORDER BY created_at LIMIT %s FOR UPDATE SKIP LOCKED", (min(BATCH, room),))
        rows = cur.fetchall()
        if not rows:
            return {"configured": True, "sent": 0, "failed": 0}
        smtp = None
        try:
            smtp = _connect()
        except Exception as exc:  # server unreachable or login refused: retry next pass
            log.warning("smtp connect failed: %s", type(exc).__name__)
        for r in rows:
            payload = r["payload"] if isinstance(r["payload"], dict) else json.loads(r["payload"])
            try:
                if smtp is None:
                    raise ConnectionError("smtp unavailable")
                if r["template"] not in TEMPLATES:
                    raise ValueError(f"unknown template {r['template']}")
                smtp.send_message(render(r["to_email"], r["template"], payload))
                cur.execute("UPDATE aav.outbound_mail SET status = 'sent', payload = payload || "
                            "jsonb_build_object('sent_at', now()) WHERE id = %s", (r["id"],))
                sent += 1
            except Exception as exc:
                attempts = int(payload.get("attempts", 0)) + 1
                status = "failed" if attempts >= MAX_ATTEMPTS or isinstance(exc, ValueError) else "queued"
                cur.execute("UPDATE aav.outbound_mail SET status = %s, payload = payload || "
                            "jsonb_build_object('attempts', %s::int, 'last_error', %s::text) WHERE id = %s",
                            (status, attempts, type(exc).__name__, r["id"]))
                failed += 1
        if smtp is not None:
            try:
                smtp.quit()
            except Exception:
                pass
    if sent or failed:
        log.info("mail pass: sent=%d failed=%d", sent, failed)
    return {"configured": True, "sent": sent, "failed": failed}


_stop = threading.Event()


def _loop() -> None:
    while not _stop.wait(settings.mail_poll_seconds):
        try:
            deliver_pending()
        except Exception as exc:  # keep the worker alive through DB restarts
            log.warning("mail pass failed: %s", type(exc).__name__)


def start() -> None:
    if not configured():
        log.warning("email delivery is off: set AAV_SMTP_HOST, AAV_MAIL_FROM and the SMTP password")
        return
    threading.Thread(target=_loop, name="aav-mailer", daemon=True).start()


def stop() -> None:
    _stop.set()
