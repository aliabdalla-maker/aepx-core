"""Bounded JSON boundary for trusted, complete IdP identity snapshots.

This parser does NOT authenticate an IdP or expose a public endpoint.
The caller must authenticate the upstream and enforce a network deadline.
"""
import json
from datetime import datetime
from uuid import UUID
from .hitl_identity_snapshot import SnapshotRejected,publish_identity_snapshot

MAX_SNAPSHOT_BYTES=4*1024*1024

def _unique_pairs(pairs):
    obj={}
    for key,value in pairs:
        if key in obj:
            raise ValueError("duplicate JSON key")
        obj[key]=value
    return obj

def parse_snapshot_payload(payload, *, max_bytes=MAX_SNAPSHOT_BYTES):
    try:
        if type(max_bytes) is not int or not 0<max_bytes<=MAX_SNAPSHOT_BYTES:
            raise ValueError("invalid byte limit")
        if not isinstance(payload,bytes) or len(payload)>max_bytes:
            raise ValueError("snapshot payload exceeds byte limit")
        data=json.loads(payload.decode("utf-8"),object_pairs_hook=_unique_pairs,
                        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite number")))
        if not isinstance(data,dict) or set(data)!={
            "tenant_id","issuer","memberships","revoked_tokens","captured_at","revision"}:
            raise ValueError("unexpected snapshot schema")
        UUID(data["tenant_id"])
        if not isinstance(data["memberships"],list) or not isinstance(data["revoked_tokens"],list):
            raise ValueError("snapshot lists required")
        if len(data["memberships"])>100000 or len(data["revoked_tokens"])>1000000:
            raise ValueError("snapshot too large")
        if type(data["revision"]) is not int:
            raise ValueError("integer revision required")
        captured_at=datetime.fromisoformat(data["captured_at"].replace("Z","+00:00"))
        if captured_at.tzinfo is None:
            raise ValueError("timezone required")
        return dict(tenant_id=data["tenant_id"],issuer=data["issuer"],
                    memberships=data["memberships"],revoked_tokens=data["revoked_tokens"],
                    captured_at=captured_at,revision=data["revision"])
    except Exception as exc:
        raise SnapshotRejected("identity snapshot payload rejected") from exc

def publish_bounded_snapshot(connection, *, payload, max_bytes=MAX_SNAPSHOT_BYTES):
    parsed=parse_snapshot_payload(payload,max_bytes=max_bytes)
    return publish_identity_snapshot(connection,**parsed)
