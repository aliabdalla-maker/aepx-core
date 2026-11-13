"""Authenticated, fail-closed HITL approval consumption HTTP boundary.

This endpoint only commits an approval consumption and outbox event; it never
executes an external action. An independently authorised worker is required.
"""
import os
from uuid import UUID
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field, field_validator
from app.hitl_oidc import verify_bearer, AuthenticationDenied
from app.hitl_authz import authorize_consume, AuthorizationDenied
from app.hitl_postgres import consume_with_outbox, ApprovalError

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

@router.post("/consume",status_code=202)
def consume(request: ConsumeRequest, authorization: str | None=Header(default=None)):
    try:
        principal=verify_bearer(authorization)
        actor=authorize_consume(principal,tenant_id=request.tenant_id)
    except (AuthenticationDenied,AuthorizationDenied,ValueError) as exc:
        raise HTTPException(status_code=403,detail="HITL authentication or authorization denied") from exc
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
        raise HTTPException(status_code=409,detail="Approval not consumable") from exc
    except Exception as exc:
        # Do not leak connection strings, SQL, tokens or tenant data.
        raise HTTPException(status_code=503,detail="HITL persistence unavailable") from exc
    return {"status":"queued","event_id":event_id}
