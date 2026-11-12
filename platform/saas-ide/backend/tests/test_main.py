"""Fast tests that never connect to PostgreSQL or a live OIDC issuer."""
import os
os.environ.setdefault("IDE_DATABASE_URL", "postgresql+psycopg://unused:unused@localhost/unused")
os.environ.setdefault("IDE_OIDC_ISSUER", "https://id.example.test")
os.environ.setdefault("IDE_OIDC_JWKS_URL", "https://id.example.test/keys")
os.environ.setdefault("IDE_OIDC_AUDIENCE", "ide-api")

from fastapi.testclient import TestClient
from fastapi import HTTPException
from app.main import app, safe_path, verified_subject


def test_health():
    assert TestClient(app).get("/health").json()["status"] == "ok"


def test_no_token_fails_closed():
    assert TestClient(app).get("/api/v1/projects", headers={"X-Tenant-ID": "alpha"}).status_code == 401


def test_invalid_token_fails_closed():
    assert TestClient(app).get("/api/v1/projects", headers={
        "X-Tenant-ID": "alpha", "Authorization": "Bearer invalid"
    }).status_code == 401


def test_reject_unsafe_workspace_paths():
    for path in ("", "/etc/passwd", "../secret", "src/../secret", "src//main.py", "src\\main.py"):
        try:
            safe_path(path)
        except HTTPException as e:
            assert e.status_code == 400
        else:
            raise AssertionError(f"Unsafe path accepted: {path!r}")
    assert safe_path("src/main.py") == "src/main.py"
