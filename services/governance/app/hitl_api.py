"""Authenticated, fail-closed HITL approval consumption HTTP boundary.

This endpoint only commits an approval consumption and outbox event; it never
executes an external action. An independently authorised worker is required.
"""
import os
from uuid import UUID
from datetime import datetime, timezone
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field, field_validator
from app.hitl_oidc import verify_bearer, AuthenticationDenied
from app.hitl_authz import authorize_consume, AuthorizationDenied
from app.hitl_postgres import consume_with_outbox, ApprovalError
from app.hitl_replay import find_matching_replay
from app.hitl_authz import authorize_request, authorize_decision
from app.hitl_lifecycle import create_request, decide_request, DecisionConflict
from app.hitl_verified_bearer_identity import verify_bearer_identity
from app.hitl_identity_policy import IdentityPolicyDenied

router=APIRouter(prefix="/hitl",tags=["hitl"])

class ConsumeRequest(BaseModel):
    tenant_id: UUID
    approval_id: UUID
    action: dict = Field(min_length=1)
    idempotency_key: str = Field(min_length=8,max_length=200)

    @field_validator("idempotency_key")
    @classmethod
    def valid_idempotency_key(cls, value: str) -> str:
        if not value.isascii() or not all(c.isalnum() or c in "-_." for c in value):
            raise ValueError("idempotency key must use ASCII letters, digits, dash, underscore or dot")
        return value

def _authoritative_identity(authorization, tenant_id):
    """Fail closed before every HITL mutation if identity authority is unavailable."""
    identity_dsn=os.getenv("HITL_IDENTITY_READ_DATABASE_URL")
    if not identity_dsn:
        raise HTTPException(status_code=503,detail="HITL identity authority unavailable")
    try:
        import psycopg
        verify_bearer_identity(
            authorization,expected_tenant=tenant_id,
            connection_factory=lambda: psycopg.connect(identity_dsn,connect_timeout=3))
    except IdentityPolicyDenied as exc:
        raise HTTPException(status_code=403,detail="HITL identity denied") from exc
    except Exception as exc:
        raise HTTPException(status_code=503,detail="HITL identity authority unavailable") from exc

@router.post("/consume",status_code=202)
def consume(request: ConsumeRequest, authorization: str | None=Header(default=None)):
    try:
        principal=verify_bearer(authorization)
        actor=authorize_consume(principal,tenant_id=request.tenant_id)
    except (AuthenticationDenied,AuthorizationDenied,ValueError) as exc:
        raise HTTPException(status_code=403,detail="HITL authentication or authorization denied") from exc
    _authoritative_identity(authorization,request.tenant_id)
    # Never fall back to in-memory state or development credentials.
    dsn=os.getenv("HITL_DATABASE_URL")
    if not dsn:
        raise HTTPException(status_code=503,detail="HITL database unavailable")
    try:
        import psycopg
        with psycopg.connect(dsn,connect_timeout=3) as connection:
            event_id=consume_with_outbox(
                connection,tenant_id=request.tenant_id,
                approval_id=request.approval_id,action=request.action,
                idempotency_key=request.idempotency_key,actor_id=actor)
    except ApprovalError as exc:
        # Only a previously committed event matching the entire verified
        # tenant/actor/action/approval tuple can be returned as a replay.
        try:
            import psycopg
            with psycopg.connect(dsn,connect_timeout=3) as connection:
                prior=find_matching_replay(
                    connection,tenant_id=request.tenant_id,
                    approval_id=request.approval_id,action=request.action,
                    idempotency_key=request.idempotency_key,actor_id=actor)
        except Exception as db_exc:
            raise HTTPException(status_code=503,detail="HITL persistence unavailable") from db_exc
        if prior is None:
            raise HTTPException(status_code=409,detail="Approval not consumable") from exc
        return {"status":"queued","event_id":prior}
    except Exception as exc:
        # Do not leak connection strings, SQL, tokens or tenant data.
        raise HTTPException(status_code=503,detail="HITL persistence unavailable") from exc
    return {"status":"queued","event_id":event_id}

class RequestApproval(BaseModel):
    tenant_id: UUID
    action: dict = Field(min_length=1)
    expires_at: datetime

class DecideApproval(BaseModel):
    tenant_id: UUID
    decision: str

def _verified(authorization,tenant_id,role):
    try:
        principal=verify_bearer(authorization)
        if role=="request":
            authorize_request(principal,tenant_id=tenant_id)
        else:
            # Role check here; self-approval is additionally enforced atomically in SQL.
            from app.hitl_authz import require_role
            require_role(principal,tenant_id=tenant_id,role="hitl:approve")
        _authoritative_identity(authorization,tenant_id)
        return principal
    except (AuthenticationDenied,AuthorizationDenied,ValueError) as exc:
        raise HTTPException(status_code=403,detail="HITL authentication or authorization denied") from exc

def _dsn():
    dsn=os.getenv("HITL_DATABASE_URL")
    if not dsn:
        raise HTTPException(status_code=503,detail="HITL database unavailable")
    return dsn

@router.post("/requests",status_code=201)
def request_approval(body: RequestApproval, authorization: str | None=Header(default=None)):
    principal=_verified(authorization,body.tenant_id,"request")
    if body.expires_at.tzinfo is None or body.expires_at<=datetime.now(timezone.utc):
        raise HTTPException(status_code=422,detail="Future timezone-aware expiry required")
    dsn=_dsn()
    try:
        import psycopg
        with psycopg.connect(dsn,connect_timeout=3) as conn:
            approval_id=create_request(conn,tenant_id=body.tenant_id,action=body.action,
                                       requester_id=principal.subject,expires_at=body.expires_at)
    except Exception as exc:
        raise HTTPException(status_code=503,detail="HITL persistence unavailable") from exc
    return {"approval_id":approval_id,"status":"pending"}

@router.post("/requests/{approval_id}/decision")
def decide_approval(approval_id: UUID, body: DecideApproval,
                    authorization: str | None=Header(default=None)):
    principal=_verified(authorization,body.tenant_id,"approve")
    if body.decision not in ("approved","rejected"):
        raise HTTPException(status_code=422,detail="Decision must be approved or rejected")
    dsn=_dsn()
    try:
        import psycopg
        with psycopg.connect(dsn,connect_timeout=3) as conn:
            decision=decide_request(conn,tenant_id=body.tenant_id,approval_id=approval_id,
                                    approver_id=principal.subject,decision=body.decision)
    except DecisionConflict as exc:
        raise HTTPException(status_code=409,detail="Approval not decidable") from exc
    except Exception as exc:
        raise HTTPException(status_code=503,detail="HITL persistence unavailable") from exc
    return {"approval_id":str(approval_id),"status":decision}
