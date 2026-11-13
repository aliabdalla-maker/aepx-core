"""Transactional publication of authoritative identity snapshots.

Only a trusted IdP synchronizer may call this function. This module does not
fetch identity data or provide a public HTTP endpoint. Its DB role must be
restricted to the required tenant-scoped tables.
"""
from datetime import datetime, timezone
from itertools import islice
from urllib.parse import urlsplit
from uuid import UUID

class SnapshotRejected(PermissionError):
    pass

def publish_identity_snapshot(connection, *, tenant_id, issuer, memberships,
                              revoked_tokens, captured_at, revision, max_age_seconds=30):
    """Replace a tenant/issuer snapshot and heartbeat in one transaction.

    memberships: sequence of subject strings (active members).
    revoked_tokens: sequence of (subject, token_id) pairs. The upstream
    authority must provide a COMPLETE revocation snapshot, not deltas.
    """
    try:
        tenant=str(UUID(str(tenant_id)))
        parsed=urlsplit(issuer) if isinstance(issuer,str) else None
        if (not parsed or parsed.scheme!="https" or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or parsed.path not in ("","/")
            or any(ch.isspace() for ch in issuer)
            or len(issuer)>512 or not isinstance(captured_at,datetime)
            or captured_at.tzinfo is None or not 0<max_age_seconds<=60
            or type(revision) is not int or not 1<=revision<=9223372036854775807):
            raise ValueError("invalid authority metadata")
        age=(datetime.now(timezone.utc)-captured_at.astimezone(timezone.utc)).total_seconds()
        if age < -5 or age > max_age_seconds:
            raise ValueError("stale or future snapshot")
        # Cap materialisation even when upstream passes infinite generators.
        members=list(islice(iter(memberships),100001))
        revoked=list(islice(iter(revoked_tokens),1000001))
        if len(members)>100000 or len(revoked)>1000000:
            raise ValueError("snapshot too large")
        if any(not isinstance(x,str) or not 8<=len(x)<=128 for x in members):
            raise ValueError("invalid subject")
        if any(not isinstance(x,(tuple,list)) or len(x)!=2 or
               not isinstance(x[0],str) or not 8<=len(x[0])<=128 or
               not isinstance(x[1],str) or not 8<=len(x[1])<=256 for x in revoked):
            raise ValueError("invalid revoked token")
        if len(set(members))!=len(members) or len(set(map(tuple,revoked)))!=len(revoked):
            raise ValueError("duplicate snapshot entries")
        with connection.cursor() as cur:
            # Lock existing authority row to serialize publishers for this scope.
            # The initial insert is conflict-safe and establishes a lock target.
            cur.execute("""INSERT INTO hitl.identity_authority_sync
                (tenant_id,issuer,synced_at,healthy)
                VALUES (%s,%s,now(),false)
                ON CONFLICT (tenant_id,issuer) DO NOTHING""",(tenant,issuer))
            cur.execute("""SELECT revision FROM hitl.identity_authority_sync
                WHERE tenant_id=%s AND issuer=%s FOR UPDATE""",(tenant,issuer))
            current=cur.fetchone()
            if not current or current[0] is None or revision<=current[0]:
                raise ValueError("snapshot revision is not newer")
            cur.execute("""UPDATE hitl.identity_authority_sync SET healthy=false
                WHERE tenant_id=%s AND issuer=%s""",(tenant,issuer))
            cur.execute("""DELETE FROM hitl.identity_memberships
                WHERE tenant_id=%s AND issuer=%s""",(tenant,issuer))
            cur.execute("""DELETE FROM hitl.identity_revocations
                WHERE tenant_id=%s AND issuer=%s""",(tenant,issuer))
            for subject in members:
                cur.execute("""INSERT INTO hitl.identity_memberships
                    (tenant_id,issuer,subject,active)
                    VALUES (%s,%s,%s,true)""",(tenant,issuer,subject))
            for subject,token_id in revoked:
                cur.execute("""INSERT INTO hitl.identity_revocations
                    (tenant_id,issuer,subject,token_id)
                    VALUES (%s,%s,%s,%s)""",(tenant,issuer,subject,token_id))
            cur.execute("""UPDATE hitl.identity_authority_sync
                SET synced_at=now(),healthy=true,revision=%s
                WHERE tenant_id=%s AND issuer=%s""",(revision,tenant,issuer))
        connection.commit()
        return True
    except Exception as exc:
        try:
            connection.rollback()
        except Exception:
            pass
        raise SnapshotRejected("authoritative identity snapshot publication denied") from exc
