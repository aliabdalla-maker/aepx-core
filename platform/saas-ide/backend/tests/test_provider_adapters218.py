"""Offline MCP provider capability contract checks."""
import pytest
from app.provider_adapters218 import capabilities, require_side_effect_contract

def test_provider_contracts_fail_closed(monkeypatch):
    monkeypatch.delenv("IDE_MCP_KNOWLEDGE_IDEMPOTENCY_CONTRACT", raising=False)
    monkeypatch.delenv("IDE_MCP_KNOWLEDGE_SIGNED_RECEIPTS", raising=False)
    monkeypatch.delenv("IDE_MCP_RECEIPT_ED25519_PUBLIC_KEY", raising=False)
    caps = capabilities("knowledge")
    assert not caps.idempotency_header and not caps.signed_outcome_receipts
    with pytest.raises(PermissionError, match="contracts"):
        require_side_effect_contract("knowledge")
    with pytest.raises(PermissionError, match="Unapproved"):
        capabilities("unknown")
    monkeypatch.setenv("IDE_MCP_KNOWLEDGE_IDEMPOTENCY_CONTRACT", "invented")
    with pytest.raises(PermissionError, match="Unknown"):
        capabilities("knowledge")
    monkeypatch.setenv("IDE_MCP_KNOWLEDGE_IDEMPOTENCY_CONTRACT", "http-header-v1")
    monkeypatch.setenv("IDE_MCP_KNOWLEDGE_SIGNED_RECEIPTS", "true")
    with pytest.raises(PermissionError, match="trust anchor"):
        require_side_effect_contract("knowledge")
    monkeypatch.setenv("IDE_MCP_RECEIPT_ED25519_PUBLIC_KEY", "configured-in-test")
    assert require_side_effect_contract("knowledge").idempotency_header
