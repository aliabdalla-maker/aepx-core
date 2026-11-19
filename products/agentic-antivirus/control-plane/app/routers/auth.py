"""Account management (FN-01, UI-09, BE-07, KPI-05 failed logins, D-12 both account models)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
import jwt
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, EmailStr, Field

from app import audit, crypto, db
from app.config import settings
from app.deps import Principal, current_user, need

router = APIRouter(prefix="/v1/auth", tags=["auth"])

MAX_FAILED = 5
LOCK_MINUTES = 15


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)
    display_name: str = Field(default="", max_length=200)
    organisation: str = Field(min_length=1, max_length=200)
    locale: str = Field(default="en", max_length=20)
    parent_msp_tenant_id: UUID | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenIn(BaseModel):
    token: str


class ResetIn(BaseModel):
    token: str
    new_password: str = Field(min_length=12, max_length=256)


class EmailIn(BaseModel):
    email: EmailStr


class ProfilePatch(BaseModel):
    display_name: str | None = Field(default=None, max_length=200)
    locale: str | None = Field(default=None, max_length=20)


class InviteIn(BaseModel):
    email: EmailStr
    role: str


class AcceptInviteIn(BaseModel):
    token: str
    password: str = Field(min_length=12, max_length=256)
    display_name: str = Field(default="", max_length=200)


class OidcIn(BaseModel):
    id_token: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _issue_token(cur, user_id, kind: str, hours: int) -> str:
    token = crypto.new_token()
    cur.execute("INSERT INTO aav.auth_tokens (user_id, kind, token_hash, expires_at) VALUES (%s, %s, %s, %s)",
                (user_id, kind, crypto.token_hash(token), _now() + timedelta(hours=hours)))
    return token


def _queue_mail(cur, to: str, template: str, token: str) -> None:
    cur.execute("INSERT INTO aav.outbound_mail (to_email, template, payload) VALUES (%s, %s, %s)",
                (to, template, json.dumps({"link": f"{settings.public_base_url}/{template}?token={token}"})))


def _consume(cur, token: str, kind: str):
    cur.execute("UPDATE aav.auth_tokens SET used_at = now() WHERE token_hash = %s AND kind = %s AND used_at IS NULL "
                "AND expires_at > now() RETURNING user_id", (crypto.token_hash(token), kind))
    row = cur.fetchone()
    if not row:
        raise HTTPException(400, "invalid or expired token")
    return row["user_id"]


def _new_session(cur, user_id) -> dict:
    token = crypto.new_token()
    expires = _now() + timedelta(hours=settings.session_hours)
    cur.execute("INSERT INTO aav.sessions (user_id, token_hash, expires_at) VALUES (%s, %s, %s)",
                (user_id, crypto.token_hash(token), expires))
    return {"access_token": token, "token_type": "bearer", "expires_at": expires.isoformat()}


@router.post("/register", status_code=201)
def register(body: RegisterIn):
    if not settings.allow_open_registration:
        raise HTTPException(403, "registration is by invitation only")
    with db.global_tx() as cur:
        cur.execute("SELECT 1 FROM aav.users WHERE email = %s", (body.email.lower(),))
        if cur.fetchone():
            raise HTTPException(409, "account exists")
        cur.execute("INSERT INTO aav.users (email, password_hash, display_name, locale) VALUES (%s, %s, %s, %s) "
                    "RETURNING id", (body.email.lower(), crypto.hash_password(body.password), body.display_name,
                                     body.locale))
        uid = cur.fetchone()["id"]
        if body.parent_msp_tenant_id:
            raise HTTPException(400, "MSP child tenants are created by the MSP via /v1/tenants")
        cur.execute("SELECT aav.bootstrap_tenant(%s, %s, NULL) AS tid", (body.organisation, uid))
        tid = cur.fetchone()["tid"]
        _queue_mail(cur, body.email.lower(), "verify-email", _issue_token(cur, uid, "email_verify", 48))
        audit.record(cur, tenant_id=None, actor=f"user:{uid}", action="account.register", target=str(uid))
    with db.tenant_tx(tid) as cur:
        audit.record(cur, tenant_id=tid, actor=f"user:{uid}", action="tenant.create", target=str(tid))
    return {"user_id": str(uid), "tenant_id": str(tid), "email_verification": "queued"}


@router.post("/verify-email")
def verify_email(body: TokenIn):
    with db.global_tx() as cur:
        uid = _consume(cur, body.token, "email_verify")
        cur.execute("UPDATE aav.users SET email_verified = true WHERE id = %s", (uid,))
        audit.record(cur, tenant_id=None, actor=f"user:{uid}", action="account.email_verified", target=str(uid))
    return {"verified": True}


@router.post("/resend-verification")
def resend_verification(body: EmailIn):
    with db.global_tx() as cur:
        cur.execute("SELECT id FROM aav.users WHERE email = %s AND NOT email_verified AND deleted_at IS NULL",
                    (body.email.lower(),))
        row = cur.fetchone()
        if row:
            _queue_mail(cur, body.email.lower(), "verify-email", _issue_token(cur, row["id"], "email_verify", 48))
    return {"status": "queued_if_account_exists"}


@router.post("/login")
def login(body: LoginIn):
    with db.global_tx() as cur:
        cur.execute("SELECT id, password_hash, failed_logins, locked_until FROM aav.users "
                    "WHERE email = %s AND deleted_at IS NULL FOR UPDATE", (body.email.lower(),))
        u = cur.fetchone()
        if u and u["locked_until"] and u["locked_until"] > _now():
            audit.record(cur, tenant_id=None, actor="anonymous", action="auth.login_locked", target=str(u["id"]))
            cur.connection.commit()
            raise HTTPException(423, "account temporarily locked")
        if not u or not crypto.verify_password(u["password_hash"], body.password):
            if u:
                failed = u["failed_logins"] + 1
                locked = _now() + timedelta(minutes=LOCK_MINUTES) if failed >= MAX_FAILED else None
                cur.execute("UPDATE aav.users SET failed_logins = %s, locked_until = %s WHERE id = %s",
                            (0 if locked else failed, locked, u["id"]))
            audit.record(cur, tenant_id=None, actor="anonymous", action="auth.login_failed",
                         target=body.email.lower())
            cur.connection.commit()  # keep the failure count and audit entry when returning 401
            raise HTTPException(401, "invalid credentials")
        cur.execute("UPDATE aav.users SET failed_logins = 0, locked_until = NULL WHERE id = %s", (u["id"],))
        sess = _new_session(cur, u["id"])
        audit.record(cur, tenant_id=None, actor=f"user:{u['id']}", action="auth.login", target=str(u["id"]))
    return sess


@router.post("/oidc")
def oidc_login(body: OidcIn):
    """Exchange a verified OIDC ID token (e.g. Google) for a session. Requires AAV_OIDC_* config."""
    if not (settings.oidc_issuer and settings.oidc_client_id and settings.oidc_jwks_url):
        raise HTTPException(503, "OIDC not configured")
    try:
        jwks = jwt.PyJWKClient(settings.oidc_jwks_url)
        key = jwks.get_signing_key_from_jwt(body.id_token).key
        claims = jwt.decode(body.id_token, key, algorithms=["RS256", "ES256"], audience=settings.oidc_client_id,
                            issuer=settings.oidc_issuer)
    except (jwt.PyJWTError, httpx.HTTPError) as exc:
        raise HTTPException(401, f"invalid id token: {type(exc).__name__}")
    if not claims.get("email") or claims.get("email_verified") is not True:
        raise HTTPException(403, "verified email required")
    email = claims["email"].lower()
    with db.global_tx() as cur:
        cur.execute("SELECT id FROM aav.users WHERE (oidc_subject = %s OR email = %s) AND deleted_at IS NULL",
                    (f"{claims['iss']}|{claims['sub']}", email))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "no account for this identity; register or accept an invitation first")
        cur.execute("UPDATE aav.users SET oidc_subject = %s, email_verified = true WHERE id = %s",
                    (f"{claims['iss']}|{claims['sub']}", row["id"]))
        sess = _new_session(cur, row["id"])
        audit.record(cur, tenant_id=None, actor=f"user:{row['id']}", action="auth.login_oidc", target=str(row["id"]))
    return sess


@router.post("/logout")
def logout(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    with db.global_tx() as cur:
        cur.execute("UPDATE aav.sessions SET revoked_at = now() WHERE token_hash = %s AND revoked_at IS NULL "
                    "RETURNING user_id", (crypto.token_hash(authorization[7:].strip()),))
        row = cur.fetchone()
        if row:
            audit.record(cur, tenant_id=None, actor=f"user:{row['user_id']}", action="auth.logout")
    return {"logged_out": bool(row)}


@router.post("/password-reset/request")
def reset_request(body: EmailIn):
    with db.global_tx() as cur:
        cur.execute("SELECT id FROM aav.users WHERE email = %s AND deleted_at IS NULL", (body.email.lower(),))
        row = cur.fetchone()
        if row:
            _queue_mail(cur, body.email.lower(), "reset-password", _issue_token(cur, row["id"], "password_reset", 1))
            audit.record(cur, tenant_id=None, actor="anonymous", action="auth.reset_requested", target=str(row["id"]))
    return {"status": "queued_if_account_exists"}


@router.post("/password-reset/confirm")
def reset_confirm(body: ResetIn):
    with db.global_tx() as cur:
        uid = _consume(cur, body.token, "password_reset")
        cur.execute("UPDATE aav.users SET password_hash = %s, failed_logins = 0, locked_until = NULL WHERE id = %s",
                    (crypto.hash_password(body.new_password), uid))
        cur.execute("UPDATE aav.sessions SET revoked_at = now() WHERE user_id = %s AND revoked_at IS NULL", (uid,))
        audit.record(cur, tenant_id=None, actor=f"user:{uid}", action="auth.password_reset", target=str(uid))
    return {"reset": True}


@router.get("/me")
def me(p: Principal = Depends(current_user)):
    with db.global_tx() as cur:
        cur.execute("SELECT id, email, email_verified, display_name, locale, created_at FROM aav.users WHERE id = %s",
                    (p.user_id,))
        user = cur.fetchone()
        cur.execute("SELECT tenant_id, tenant_name, role FROM aav.user_tenants(%s)", (p.user_id,))
        tenants: dict = {}
        for r in cur.fetchall():
            tenants.setdefault(str(r["tenant_id"]), {"tenant_id": str(r["tenant_id"]), "name": r["tenant_name"],
                                                     "roles": []})["roles"].append(r["role"])
    return {**user, "tenants": list(tenants.values())}


@router.patch("/me")
def update_profile(body: ProfilePatch, p: Principal = Depends(current_user)):
    from app.i18n import LOCALES
    if body.locale is not None and body.locale not in LOCALES:
        raise HTTPException(422, "unsupported locale")
    with db.global_tx() as cur:
        cur.execute("UPDATE aav.users SET display_name = COALESCE(%s, display_name), locale = COALESCE(%s, locale) "
                    "WHERE id = %s", (body.display_name, body.locale, p.user_id))
        audit.record(cur, tenant_id=None, actor=p.actor, action="account.profile_update",
                     detail=body.model_dump(exclude_none=True))
    return {"updated": True}


@router.delete("/me")
def delete_account(p: Principal = Depends(current_user)):
    """Soft-delete and anonymise; revoke sessions. Memberships are removed through each tenant."""
    with db.global_tx() as cur:
        cur.execute("UPDATE aav.users SET deleted_at = now(), email = 'deleted+' || id || '@invalid', "
                    "password_hash = NULL, oidc_subject = NULL, display_name = '' WHERE id = %s", (p.user_id,))
        cur.execute("UPDATE aav.sessions SET revoked_at = now() WHERE user_id = %s AND revoked_at IS NULL",
                    (p.user_id,))
        cur.execute("SELECT tenant_id FROM aav.user_tenants(%s)", (p.user_id,))
        tids = {r["tenant_id"] for r in cur.fetchall()}
        audit.record(cur, tenant_id=None, actor=p.actor, action="account.delete", target=str(p.user_id))
    for tid in tids:
        with db.tenant_tx(tid) as cur:
            cur.execute("DELETE FROM aav.memberships WHERE user_id = %s", (p.user_id,))
            audit.record(cur, tenant_id=tid, actor=p.actor, action="membership.remove_on_delete",
                         target=str(p.user_id))
    return {"deleted": True}


@router.post("/invitations", status_code=201)
def invite(body: InviteIn, p: Principal = Depends(need("users.manage"))):
    from app.rbac import ROLES
    if body.role not in ROLES:
        raise HTTPException(422, "unknown role")
    email = body.email.lower()
    with db.global_tx() as cur:
        cur.execute("SELECT id FROM aav.users WHERE email = %s AND deleted_at IS NULL", (email,))
        row = cur.fetchone()
        if row:
            uid = row["id"]
        else:
            cur.execute("INSERT INTO aav.users (email) VALUES (%s) RETURNING id", (email,))
            uid = cur.fetchone()["id"]
            _queue_mail(cur, email, "accept-invite", _issue_token(cur, uid, "invite", 72))
    with db.tenant_tx(p.tenant_id) as cur:
        cur.execute("INSERT INTO aav.memberships (tenant_id, user_id, role) VALUES (%s, %s, %s) "
                    "ON CONFLICT DO NOTHING", (p.tenant_id, uid, body.role))
        audit.record(cur, tenant_id=p.tenant_id, actor=p.actor, action="users.invite", target=str(uid),
                     detail={"role": body.role})
    return {"user_id": str(uid), "role": body.role}


@router.post("/invitations/accept")
def accept_invite(body: AcceptInviteIn):
    with db.global_tx() as cur:
        uid = _consume(cur, body.token, "invite")
        cur.execute("UPDATE aav.users SET password_hash = %s, email_verified = true, display_name = %s WHERE id = %s",
                    (crypto.hash_password(body.password), body.display_name, uid))
        sess = _new_session(cur, uid)
        audit.record(cur, tenant_id=None, actor=f"user:{uid}", action="users.invite_accepted", target=str(uid))
    return sess
