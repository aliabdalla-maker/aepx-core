"""Fail-closed provider evidence verifier adapter for remote HITL reconciliation.

The provider status reader must be trusted and independent of the submitted
reconciliation request. This module performs no external network operations.
"""
from uuid import UUID
import re

class ProviderEvidenceDenied(PermissionError):
    pass

_OPAQUE=re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}\Z")

def provider_evidence_verifier(*,trusted_provider,read_provider_status):
    """Return callback accepted by reconcile_remote(verify_evidence=...).

    read_provider_status MUST independently query a trusted provider or signed
    receipt store using tenant/event/provider/idempotency key. It must return a
    dict with exact matching identifiers, terminal state, evidence reference
    and an authoritative boolean verified=True. Never construct this dict
    directly from HTTP request fields.
    """
    if not isinstance(trusted_provider,str) or not trusted_provider.strip():
        raise ProviderEvidenceDenied("trusted provider required")
    if not callable(read_provider_status):
        raise ProviderEvidenceDenied("trusted status reader required")

    def verify(*,tenant_id,event_id,provider,idempotency_key,verified_state,
               evidence_reference,reviewer_id):
        try:
            tenant=str(UUID(str(tenant_id)))
            event=str(UUID(str(event_id)))
            if (provider!=trusted_provider or verified_state not in ("confirmed","failed_safe")
                or not isinstance(idempotency_key,str) or not 8<=len(idempotency_key)<=200
                or not isinstance(evidence_reference,str)
                or _OPAQUE.fullmatch(evidence_reference) is None
                or not isinstance(reviewer_id,str) or _OPAQUE.fullmatch(reviewer_id) is None):
                return False
            evidence=read_provider_status(tenant_id=tenant,event_id=event,
                provider=trusted_provider,idempotency_key=idempotency_key)
            if not isinstance(evidence,dict) or evidence.get("verified") is not True:
                return False
            return (evidence.get("tenant_id")==tenant
                and evidence.get("event_id")==event
                and evidence.get("provider")==trusted_provider
                and evidence.get("idempotency_key")==idempotency_key
                and evidence.get("state")==verified_state
                and evidence.get("evidence_reference")==evidence_reference)
        except Exception:
            return False
    return verify
