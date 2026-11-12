"""Explicit, fail-closed MCP provider capability contracts.

Never infer idempotency from a header. No live providers are enabled by default.
"""
import os
from dataclasses import dataclass

@dataclass(frozen=True)
class ProviderCapabilities:
    server: str
    idempotency_header: bool
    signed_outcome_receipts: bool

def capabilities(server: str) -> ProviderCapabilities:
    from .agent_runtime import APPROVED_SERVERS
    if server not in APPROVED_SERVERS:
        raise PermissionError("Unapproved MCP provider")
    prefix = "IDE_MCP_" + server.upper().replace("-", "_")
    contract = os.getenv(prefix + "_IDEMPOTENCY_CONTRACT", "")
    if contract not in ("", "http-header-v1"):
        raise PermissionError("Unknown provider idempotency contract")
    signed = os.getenv(prefix + "_SIGNED_RECEIPTS") == "true"
    return ProviderCapabilities(server, contract == "http-header-v1", signed)

def require_side_effect_contract(server: str) -> ProviderCapabilities:
    """Enforce explicit opt-in for side-effecting tools; never assume deduplication."""
    caps = capabilities(server)
    if not caps.idempotency_header or not caps.signed_outcome_receipts:
        raise PermissionError("Provider idempotency and signed receipt contracts required")
    if not os.getenv("IDE_MCP_RECEIPT_ED25519_PUBLIC_KEY"):
        raise PermissionError("Provider receipt trust anchor missing")
    return caps
