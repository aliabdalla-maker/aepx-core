"""Request authentication and tenant authorisation dependencies."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, HTTPException

from app import crypto, db, rbac


@dataclass
class Principal:
    user_id: UUID
    email: str
    tenant_id: UUID | None
    roles: set[str]

    @property
    def actor(self) -> str:
        return f"user:{self.user_id}"

    def require(self, permission: str) -> None:
        if not rbac.allowed(self.roles, permission):
            raise HTTPException(403, f"permission denied: {permission}")


def _session_user(authorization: str | None) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    token = authorization[7:].strip()
    with db.global_tx() as cur:
        cur.execute(
            "SELECT u.id, u.email, u.email_verified FROM aav.sessions s JOIN aav.users u ON u.id = s.user_id "
            "WHERE s.token_hash = %s AND s.revoked_at IS NULL AND s.expires_at > now() AND u.deleted_at IS NULL",
            (crypto.token_hash(token),))
        row = cur.fetchone()
    if not row:
        raise HTTPException(401, "invalid or expired session")
    return row


def current_user(authorization: str | None = Header(default=None)) -> Principal:
    row = _session_user(authorization)
    return Principal(row["id"], row["email"], None, set())


def tenant_principal(authorization: str | None = Header(default=None),
                     x_tenant_id: str | None = Header(default=None)) -> Principal:
    row = _session_user(authorization)
    if not row["email_verified"]:
        raise HTTPException(403, "email not verified")
    if not x_tenant_id:
        raise HTTPException(400, "X-Tenant-Id header required")
    try:
        tid = UUID(x_tenant_id)
    except ValueError:
        raise HTTPException(400, "invalid tenant id")
    with db.global_tx() as cur:
        cur.execute("SELECT role FROM aav.user_tenants(%s) WHERE tenant_id = %s", (row["id"], tid))
        roles = {r["role"] for r in cur.fetchall()}
    if not roles:
        # Cross-tenant request: indistinguishable from a non-existent tenant.
        raise HTTPException(404, "tenant not found")
    return Principal(row["id"], row["email"], tid, roles)


def need(permission: str):
    def dep(p: Principal = Depends(tenant_principal)) -> Principal:
        p.require(permission)
        return p
    return dep
