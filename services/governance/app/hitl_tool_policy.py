"""Fail-closed HITL event policy boundary, without network execution.

A trusted dispatcher can wrap an injected delivery function with this guard.
The guard does not provide durable deduplication or grant permission to execute
real external effects: adapters must enforce their own idempotency contract.
"""
import os
from uuid import UUID

class ToolPolicyDenied(PermissionError):
    pass

def guarded_adapter(deliver,*,allowed_tenants,allowed_action_hashes):
    """Wrap a trusted adapter with explicit tenant and action allowlists.

    The action hash must originate from an independently verified approval.
    Never populate these sets from untrusted event payloads.
    """
    if not callable(deliver):
        raise TypeError("trusted adapter required")
    tenants=frozenset(str(UUID(str(t))) for t in allowed_tenants)
    hashes=frozenset(allowed_action_hashes)
    if not tenants or not hashes or any(
        not isinstance(h,str) or len(h)!=64 or
        any(c not in "0123456789abcdef" for c in h) for h in hashes
    ):
        raise ValueError("explicit tenants and sha256 action hashes required")

    def guarded(*,event_id,topic,payload,tenant_id):
        if os.getenv("HITL_EXTERNAL_EFFECTS_ENABLED")!="yes":
            raise ToolPolicyDenied("external delivery kill switch is disabled")
        try:
            tenant=str(UUID(str(tenant_id)))
            event=str(UUID(str(event_id)))
            approval=str(UUID(str(payload["approval_id"])))
            action_hash=payload["action_hash"]
            actor=payload["actor_id"]
        except (TypeError,ValueError,KeyError,AttributeError) as exc:
            raise ToolPolicyDenied("malformed approval event") from exc
        if (topic!="hitl.approval.consumed" or tenant not in tenants
            or action_hash not in hashes or not isinstance(actor,str)
            or not actor.strip() or not approval):
            raise ToolPolicyDenied("event not permitted")
        # The adapter is responsible for independently checking the approval
        # and deduplicating event_id durably at the side-effect boundary.
        return deliver(event_id=event,topic=topic,payload=payload,tenant_id=tenant)
    return guarded
