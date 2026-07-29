from fastapi import FastAPI, HTTPException
import jwt
import time
import uuid
import os

from app.did import create_did, resolve_did

SECRET = os.getenv("IDENTITY_JWT_SECRET", "dev-only-change-me")  # replace with Vault before any pilot
app = FastAPI(title="AEP-X Identity Service", version="0.0.1")


@app.get("/health")
def health():
    return {"status": "ok", "service": "identity"}


@app.post("/token")
def issue_token(subject: str):
    payload = {"sub": subject, "iat": int(time.time()), "jti": str(uuid.uuid4())}
    return {"access_token": jwt.encode(payload, SECRET, algorithm="HS256"), "token_type": "bearer"}


@app.post("/did")
def issue_did():
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
