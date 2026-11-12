"""Adversarial Phase 2.5 egress and default-deny tests."""
import os
os.environ.setdefault("IDE_DATABASE_URL","postgresql+psycopg://unused:unused@localhost/unused")
os.environ.setdefault("IDE_OIDC_ISSUER","https://id.example.test")
os.environ.setdefault("IDE_OIDC_JWKS_URL","https://id.example.test/keys")
os.environ.setdefault("IDE_OIDC_AUDIENCE","ide-api")
import pytest
from app.egress25 import validate_https_destination, assert_egress_configured

@pytest.mark.parametrize("url",[
    "http://api.example.test/","https://localhost/","https://127.0.0.1/",
    "https://169.254.169.254/latest/meta-data","https://api.example.test@localhost/",
    "https://api.example.test.evil.test/","https://api.example.test./",
    "https://api.example.test/#fragment","https://api.example.test:443@evil.test/"
])
def test_untrusted_destinations_denied(url):
    with pytest.raises(PermissionError):
        validate_https_destination(url,allowed_hosts={"api.example.test"})

def test_explicit_destination_allowlist():
    assert validate_https_destination("https://api.example.test/v1",allowed_hosts={"api.example.test"})=="https://api.example.test/v1"

def test_default_egress_disabled(monkeypatch):
    monkeypatch.delenv("IDE_EXTERNAL_EXECUTION_ENABLED",raising=False)
    with pytest.raises(PermissionError):
        assert_egress_configured()
