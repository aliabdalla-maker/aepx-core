"""P01/P08: public auth-options and version endpoints (offline, no DB, no IdP)."""
import os
os.environ.setdefault("IDE_DATABASE_URL", "postgresql+psycopg://unused:unused@localhost/unused")
os.environ.setdefault("IDE_OIDC_ISSUER", "https://id.example.test")
os.environ.setdefault("IDE_OIDC_JWKS_URL", "https://id.example.test/keys")
os.environ.setdefault("IDE_OIDC_AUDIENCE", "ide-api")

from fastapi.testclient import TestClient
from app.main import app

FLAGS = ["IDE_AUTH_GOOGLE_ENABLED", "IDE_AUTH_GITHUB_ENABLED", "IDE_AUTH_PASSWORD_RESET_ENABLED",
         "IDE_AUTH_REGISTRATION_DISABLED", "IDE_AUTH_MFA_AVAILABLE", "IDE_RELEASE_SHA"]


def _clear(monkeypatch):
    for f in FLAGS:
        monkeypatch.delenv(f, raising=False)


def test_auth_options_default_hides_unconfigured_providers(monkeypatch):
    _clear(monkeypatch)
    r = TestClient(app).get("/api/v1/auth-options")
    assert r.status_code == 200
    assert r.json() == {"google": False, "github": False, "password_reset": False,
                        "registration": True, "mfa": False}


def test_auth_options_reflects_flags_without_leaking_secrets(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("IDE_AUTH_GOOGLE_ENABLED", "true")
    monkeypatch.setenv("IDE_AUTH_PASSWORD_RESET_ENABLED", "1")
    monkeypatch.setenv("IDE_AUTH_REGISTRATION_DISABLED", "yes")
    monkeypatch.setenv("AEPX_GOOGLE_CLIENT_SECRET", "must-never-appear")
    body = TestClient(app).get("/api/v1/auth-options").text
    assert "must-never-appear" not in body
    j = TestClient(app).get("/api/v1/auth-options").json()
    assert j["google"] and j["password_reset"] and not j["registration"] and not j["github"]


def test_auth_options_requires_no_token(monkeypatch):
    _clear(monkeypatch)
    assert TestClient(app).get("/api/v1/auth-options", headers={"Authorization": "Bearer junk"}).status_code == 200


def test_version_reports_valid_sha_only(monkeypatch):
    _clear(monkeypatch)
    c = TestClient(app)
    assert c.get("/api/v1/version").json()["release_sha"] is None
    monkeypatch.setenv("IDE_RELEASE_SHA", "0F9044C")
    assert c.get("/api/v1/version").json()["release_sha"] == "0f9044c"
    monkeypatch.setenv("IDE_RELEASE_SHA", "<script>alert(1)</script>")
    assert c.get("/api/v1/version").json()["release_sha"] is None
    monkeypatch.setenv("IDE_RELEASE_SHA", "abc")
    assert c.get("/api/v1/version").json()["release_sha"] is None
