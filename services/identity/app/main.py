from fastapi import FastAPI
import jwt
import time
import uuid
import os

SECRET = os.getenv("IDENTITY_JWT_SECRET", "dev-only-change-me")  # replace with Vault before any pilot
app = FastAPI(title="AEP-X Identity Service", version="0.0.1")


@app.get("/health")
def health():
    return {"status": "ok", "service": "identity"}


@app.post("/token")
def issue_token(subject: str):
    payload = {"sub": subject, "iat": int(time.time()), "jti": str(uuid.uuid4())}
    return {"access_token": jwt.encode(payload, SECRET, algorithm="HS256"), "token_type": "bearer"}
