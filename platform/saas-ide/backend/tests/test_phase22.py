"""Phase 2.2 pure governance tests: no credentials, DB or network required."""
import os
os.environ.setdefault("IDE_DATABASE_URL","postgresql+psycopg://unused:unused@localhost/unused")
os.environ.setdefault("IDE_OIDC_ISSUER","https://id.example.test")
os.environ.setdefault("IDE_OIDC_JWKS_URL","https://id.example.test/keys")
os.environ.setdefault("IDE_OIDC_AUDIENCE","ide-api")
import pytest
from app.phase22 import digest_arguments
from app.security22 import validate_public_ip, validate_endpoint, Budget

def test_digest_canonical_and_bound():
    assert digest_arguments({"a":1,"b":2})==digest_arguments({"b":2,"a":1})
    assert digest_arguments({"a":1})!=digest_arguments({"a":2})
    with pytest.raises(ValueError):
        digest_arguments({"payload":"x"*4100})
    with pytest.raises(ValueError):
        digest_arguments({"bad":float("nan")})

def test_budget_fails_closed():
    with pytest.raises(ValueError): Budget(max_tokens=0,max_cost_usd=0.1,timeout_seconds=10)
    with pytest.raises(ValueError): Budget(max_tokens=100,max_cost_usd=-1,timeout_seconds=10)
    assert Budget(max_tokens=100,max_cost_usd=1,timeout_seconds=10).max_tokens==100

def test_egress_rejects_private():
    for ip in ("127.0.0.1","10.0.0.1","169.254.169.254","::1","192.168.0.1"):
        with pytest.raises(ValueError): validate_public_ip(ip)
    assert validate_public_ip("8.8.8.8")=="8.8.8.8"
    with pytest.raises(ValueError): validate_endpoint("http://example.com")
    with pytest.raises(ValueError): validate_endpoint("https://127.0.0.1/mcp")
