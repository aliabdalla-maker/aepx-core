from fastapi import FastAPI, HTTPException, Header
import jwt
import time
import uuid
import os
import hmac

from app.did import create_did, resolve_did

SECRET = os.getenv("IDENTITY_JWT_SECRET", "dev-only-change-me")
if os.getenv("AEPX_SECURE_MODE") == "true":
    if len(SECRET) < 32 or SECRET == "dev-only-change-me":
        raise RuntimeError("IDENTITY_JWT_SECRET must be a strong secret in secure mode")
app = FastAPI(title="AEP-X Identity Service", version="0.0.1")


@app.get("/health")
def health():
    return {"status": "ok", "service": "identity"}


@app.post("/token")
def issue_token(subject: str, x_aepx_service_key: str | None = Header(default=None)):
    if os.getenv("AEPX_SECURE_MODE") == "true":
        expected = os.getenv("AEPX_INTERNAL_SERVICE_KEY", "")
        if len(expected) < 32 or not hmac.compare_digest(x_aepx_service_key or "", expected):
            raise HTTPException(status_code=403, detail="Service authentication required")
    payload = {"sub": subject, "iat": int(time.time()), "jti": str(uuid.uuid4())}
    return {"access_token": jwt.encode(payload, SECRET, algorithm="HS256"), "token_type": "bearer"}


@app.post("/did")
def issue_did(x_aepx_service_key: str | None = Header(default=None)):
    if os.getenv("AEPX_SECURE_MODE") == "true":
        expected = os.getenv("AEPX_INTERNAL_SERVICE_KEY", "")
        if len(expected) < 32 or not hmac.compare_digest(x_aepx_service_key or "", expected):
            raise HTTPException(status_code=403, detail="Service authentication required")
    # RFC-0006 — did:key: self-certifying, no chain or registry needed to
    # resolve it (see app/did.py). Returns the private key once; it is
    # never persisted server-side.
    return create_did()


@app.get("/did/{did}")
def get_did(did: str):
    try:
        return resolve_did(did)
    except ValueError as e:
        raise HTTPException(400, str(e))
