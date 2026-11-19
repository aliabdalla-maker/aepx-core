"""Fail-closed transport boundary for trusted IdP snapshot ingestion.

Only accepts an injected, audited transport with verified TLS and egress policy.
No default HTTP client, DNS resolution or external network access is provided.
"""
from dataclasses import dataclass
from math import isfinite
from .hitl_idp_signed_connector import (
    validate_pinned_snapshot_url,publish_signed_idp_snapshot)
from .hitl_identity_payload import MAX_SNAPSHOT_BYTES
from .hitl_identity_snapshot import SnapshotRejected

@dataclass(frozen=True)
class SnapshotResponse:
    status_code: int
    body: bytes
    signature: str
    final_url: str

def ingest_trusted_idp_snapshot(connection, *, fetch, url, expected_host,
                                tenant_id, issuer, secret,
                                max_bytes=MAX_SNAPSHOT_BYTES,
                                connect_timeout=3, total_timeout=10):
    """Fetch and publish one signed complete snapshot, with no fallback.

    fetch is a trusted transport callable that MUST enforce the supplied
    timeouts, TLS peer verification, pinned network egress, no redirects,
    and max_bytes *during* streaming. The response is rechecked here.
    """
    try:
        if (not callable(fetch) or type(max_bytes) is not int
            or not 0<max_bytes<=MAX_SNAPSHOT_BYTES
            or type(connect_timeout) not in (int,float)
            or type(total_timeout) not in (int,float)
            or not isfinite(connect_timeout) or not isfinite(total_timeout)
            or not 0<connect_timeout<=3 or not connect_timeout<=total_timeout<=10):
            raise ValueError("invalid trusted transport configuration")
        validated=validate_pinned_snapshot_url(url,expected_host=expected_host)
        response=fetch(url=validated,max_bytes=max_bytes,
                       connect_timeout=connect_timeout,total_timeout=total_timeout,
                       follow_redirects=False)
        if (not isinstance(response,SnapshotResponse)
            or type(response.status_code) is not int or response.status_code!=200
            or response.final_url!=validated
            or not isinstance(response.body,bytes)
            or len(response.body)>max_bytes
            or not isinstance(response.signature,str)):
            raise ValueError("untrusted snapshot transport response")
        return publish_signed_idp_snapshot(
            connection,payload=response.body,signature=response.signature,
            secret=secret,expected_tenant=tenant_id,
            expected_issuer=issuer,max_bytes=max_bytes)
    except Exception as exc:
        raise SnapshotRejected("trusted IdP transport denied") from exc
