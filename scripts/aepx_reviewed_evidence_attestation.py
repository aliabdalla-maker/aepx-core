"""Offline HMAC attestation for five reviewed-stage evidence digests.

The verification key must stay inside a trusted verifier service. No approvals,
database writes, provider dispatch, network or autonomous execution.
"""
import hashlib
import hmac
import json
import re
import time

STAGES=("requirements","design","patch_proposed","tests_recorded","reviewed")
DIGEST=re.compile(r"^sha256:[0-9a-f]{64}$")
IDENTIFIER=re.compile(r"^[A-Za-z0-9_-]{1,128}$")
TENANT=re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

class AttestationDenied(ValueError):
    pass

def canonical_attestation(envelope):
    if not isinstance(envelope,dict) or set(envelope)!={"tenant_id","iteration_number","lease_fence","worker_id","reviewer_id","expires_at","stage_digests"}:
        raise AttestationDenied("invalid attestation shape")
    if not isinstance(envelope["tenant_id"],str) or not TENANT.fullmatch(envelope["tenant_id"]):
        raise AttestationDenied("invalid tenant")
    for key in ("iteration_number","lease_fence","expires_at"):
        value=envelope[key]
        if type(value) is not int or value<=0:
            raise AttestationDenied("invalid attestation number")
    if envelope["iteration_number"]>10000:
        raise AttestationDenied("iteration exceeds limit")
    for key in ("worker_id","reviewer_id"):
        if not isinstance(envelope[key],str) or not IDENTIFIER.fullmatch(envelope[key]):
            raise AttestationDenied("invalid principal reference")
    digests=envelope["stage_digests"]
    if not isinstance(digests,dict) or set(digests)!=set(STAGES):
        raise AttestationDenied("incomplete stage digest set")
    if any(not isinstance(digests[s],str) or not DIGEST.fullmatch(digests[s]) for s in STAGES):
        raise AttestationDenied("invalid stage digest")
    return json.dumps(envelope,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode("ascii")

def verify_reviewed_attestation(envelope,signature,verification_key,*,tenant_id,iteration_number,lease_fence,worker_id,stage_digests,now=None):
    """Verify scope, freshness, stage digests and HMAC. Not human approval."""
    payload=canonical_attestation(envelope)
    if not isinstance(verification_key,bytes) or len(verification_key)<32:
        raise AttestationDenied("weak or missing verification key")
    if not isinstance(signature,str) or not re.fullmatch(r"[0-9a-f]{64}",signature):
        raise AttestationDenied("invalid signature")
    if (envelope["tenant_id"]!=tenant_id or
        type(iteration_number) is not int or envelope["iteration_number"]!=iteration_number or
        type(lease_fence) is not int or envelope["lease_fence"]!=lease_fence or
        envelope["worker_id"]!=worker_id or envelope["stage_digests"]!=stage_digests):
        raise AttestationDenied("attestation scope mismatch")
    current=int(time.time()) if now is None else now
    if type(current) is not int or current<0 or current>=envelope["expires_at"]:
        raise AttestationDenied("attestation expired")
    expected=hmac.new(verification_key,payload,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,signature):
        raise AttestationDenied("attestation signature mismatch")
    return True

def verify_reviewed_evidence_attestation(state,number,root,manifest,envelope,signature,verification_key,*,tenant_id,lease_fence,worker_id,now=None):
    """Verify bytes first, then attestation binding to those exact ledger digests."""
    try:
        from scripts.aepx_engineering_evidence import verify_reviewed_iteration_artifacts
        verify_reviewed_iteration_artifacts(state,number,root,manifest)
    except (ValueError,OSError) as exc:
        raise AttestationDenied("reviewed evidence verification failed") from exc
    digests=dict(state["iterations"][number-1]["evidence"])
    return verify_reviewed_attestation(
        envelope,signature,verification_key,tenant_id=tenant_id,
        iteration_number=number,lease_fence=lease_fence,
        worker_id=worker_id,stage_digests=digests,now=now)
