"""Trusted IdP snapshot transport adapter using HMAC-authenticated payloads.

The caller owns network transport, mTLS, DNS/egress policy and deadlines.
The configured secret must be provisioned outside source control.
"""
import hashlib
import hmac
from urllib.parse import urlsplit
from uuid import UUID
from .hitl_identity_payload import MAX_SNAPSHOT_BYTES,parse_snapshot_payload
from .hitl_identity_snapshot import SnapshotRejected,publish_identity_snapshot

def publish_signed_idp_snapshot(connection, *, payload, signature, secret,
                                expected_tenant, expected_issuer,
                                max_bytes=MAX_SNAPSHOT_BYTES):
    try:
        if not isinstance(secret,bytes) or len(secret)<32:
            raise ValueError("strong shared secret required")
        if not isinstance(signature,str) or len(signature)!=64:
            raise ValueError("invalid signature")
        if not isinstance(payload,bytes) or len(payload)>max_bytes:
            raise ValueError("invalid payload")
        supplied=bytes.fromhex(signature)
        expected=hmac.new(secret,payload,hashlib.sha256).digest()
        if not hmac.compare_digest(supplied,expected):
            raise ValueError("invalid payload authentication")
        parsed=parse_snapshot_payload(payload,max_bytes=max_bytes)
        if (UUID(str(parsed["tenant_id"]))!=UUID(str(expected_tenant))
            or parsed["issuer"]!=expected_issuer):
            raise ValueError("snapshot scope mismatch")
        return publish_identity_snapshot(connection,**parsed)
    except Exception as exc:
        raise SnapshotRejected("signed IdP snapshot denied") from exc

def validate_pinned_snapshot_url(url, *, expected_host):
    """Validate configured origin; caller MUST separately enforce DNS/egress."""
    try:
        parsed=urlsplit(url)
        if (not isinstance(url,str) or parsed.scheme!="https"
            or parsed.hostname!=expected_host or parsed.port not in (None,443)
            or parsed.username is not None or parsed.password is not None
            or parsed.fragment or any(ch.isspace() for ch in url)):
            raise ValueError("invalid pinned snapshot origin")
        return url
    except Exception as exc:
        raise SnapshotRejected("untrusted snapshot URL") from exc
