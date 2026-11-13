"""Guardrail tests: external worker cannot claim jobs without a trusted gate."""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock
import pytest
os.environ.setdefault("IDE_DATABASE_URL","postgresql+psycopg://unused:unused@localhost/unused")
os.environ.setdefault("IDE_OIDC_ISSUER","https://id.example.test")
os.environ.setdefault("IDE_OIDC_JWKS_URL","https://id.example.test/keys")
os.environ.setdefault("IDE_OIDC_AUDIENCE","ide-api")
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.governed_worker import execute_next

def test_external_worker_denies_without_authorization_callback(monkeypatch):
    for key in ("IDE_EXTERNAL_EXECUTION_ENABLED","IDE_GOVERNED_WORKER_ENABLED",
                "IDE_EGRESS_GATEWAY_VERIFIED","IDE_PROVIDER_USAGE_RECONCILIATION_ENABLED"):
        monkeypatch.setenv(key,"true")
    monkeypatch.setenv("IDE_WORKER_MAX_TOKENS","100")
    monkeypatch.setenv("IDE_WORKER_MAX_MICROUSD","1000")
    monkeypatch.setenv("IDE_WORKER_TIMEOUT_SECONDS","5")
    with pytest.raises(PermissionError,match="pre-dispatch"):
        execute_next("alpha",inference=MagicMock())
