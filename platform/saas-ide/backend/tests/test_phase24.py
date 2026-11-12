"""Adversarial fail-closed checks for the governed entrypoint."""
import os
os.environ.setdefault("IDE_DATABASE_URL","postgresql+psycopg://unused:unused@localhost/unused")
os.environ.setdefault("IDE_OIDC_ISSUER","https://id.example.test")
os.environ.setdefault("IDE_OIDC_JWKS_URL","https://id.example.test/keys")
os.environ.setdefault("IDE_OIDC_AUDIENCE","ide-api")
import pytest
from app.governed_worker import execute_next

def test_default_disabled(monkeypatch):
    for key in ("IDE_EXTERNAL_EXECUTION_ENABLED","IDE_GOVERNED_WORKER_ENABLED"):
        monkeypatch.delenv(key,raising=False)
    with pytest.raises(PermissionError):
        execute_next("alpha")

def test_missing_egress_gateway_denied(monkeypatch):
    monkeypatch.setenv("IDE_EXTERNAL_EXECUTION_ENABLED","true")
    monkeypatch.setenv("IDE_GOVERNED_WORKER_ENABLED","true")
    monkeypatch.delenv("IDE_EGRESS_GATEWAY_VERIFIED",raising=False)
    with pytest.raises(PermissionError):
        execute_next("alpha")

def test_missing_provider_reconciliation_denied(monkeypatch):
    for key in ("IDE_EXTERNAL_EXECUTION_ENABLED","IDE_GOVERNED_WORKER_ENABLED","IDE_EGRESS_GATEWAY_VERIFIED"):
        monkeypatch.setenv(key,"true")
    monkeypatch.delenv("IDE_PROVIDER_USAGE_RECONCILIATION_ENABLED",raising=False)
    with pytest.raises(PermissionError):
        execute_next("alpha")

def test_unconfigured_budget_denied(monkeypatch):
    for key in ("IDE_EXTERNAL_EXECUTION_ENABLED","IDE_GOVERNED_WORKER_ENABLED","IDE_EGRESS_GATEWAY_VERIFIED","IDE_PROVIDER_USAGE_RECONCILIATION_ENABLED"):
        monkeypatch.setenv(key,"true")
    for key in ("IDE_WORKER_MAX_TOKENS","IDE_WORKER_MAX_MICROUSD","IDE_WORKER_TIMEOUT_SECONDS"):
        monkeypatch.delenv(key,raising=False)
    with pytest.raises(ValueError):
        execute_next("alpha")
