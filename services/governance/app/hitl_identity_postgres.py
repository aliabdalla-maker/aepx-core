"""Authoritative tenant membership and JWT revocation checks using PostgreSQL.

The connection factory must use a restricted, non-owner identity-read role.
The database must be maintained by an independent trusted identity service.
"""
from uuid import UUID

# Authority freshness is checked in the database, not the application clock.
_AUTHORITY_FRESH = """SELECT EXISTS(
    SELECT 1 FROM hitl.identity_authority_sync
    WHERE tenant_id=%s AND issuer=%s AND healthy IS TRUE
      AND synced_at >= now() - interval '60 seconds')"""
from .hitl_identity_policy import enforce_identity_policy,IdentityPolicyDenied

def postgres_identity_verifiers(connection_factory):
    if not callable(connection_factory):
        raise IdentityPolicyDenied("trusted identity connection required")

    def membership(*,subject,tenant_id,issuer):
        try:
            tenant=str(UUID(str(tenant_id)))
            with connection_factory() as conn:
                with conn.cursor() as cur:
                    cur.execute(_AUTHORITY_FRESH,(tenant,issuer))
                    fresh=cur.fetchone()
                    if not fresh or fresh[0] is not True:
                        return False
                    cur.execute("""SELECT EXISTS(
                        SELECT 1 FROM hitl.identity_memberships
                        WHERE tenant_id=%s AND subject=%s AND issuer=%s
                          AND active IS TRUE)""",(tenant,subject,issuer))
                    row=cur.fetchone()
                    return bool(row and row[0] is True)
        except Exception:
            return False

    def not_revoked(*,subject,tenant_id,issuer,token_id):
        try:
            tenant=str(UUID(str(tenant_id)))
            with connection_factory() as conn:
                with conn.cursor() as cur:
                    cur.execute(_AUTHORITY_FRESH,(tenant,issuer))
                    fresh=cur.fetchone()
                    if not fresh or fresh[0] is not True:
                        return False
                    cur.execute("""SELECT EXISTS(
                        SELECT 1 FROM hitl.identity_revocations
                        WHERE tenant_id=%s AND subject=%s AND issuer=%s
                          AND token_id=%s)""",(tenant,subject,issuer,token_id))
                    row=cur.fetchone()
                    return bool(row and row[0] is False)
        except Exception:
            return False
    return membership,not_revoked

# One PostgreSQL statement means freshness, membership and revocation share
# the same statement-level MVCC snapshot (READ COMMITTED or stronger).
_ATOMIC_IDENTITY = """SELECT (
    EXISTS (SELECT 1 FROM hitl.identity_authority_sync
      WHERE tenant_id=%s AND issuer=%s AND healthy IS TRUE
        AND synced_at >= now() - interval '60 seconds')
    AND EXISTS (SELECT 1 FROM hitl.identity_memberships
      WHERE tenant_id=%s AND subject=%s AND issuer=%s AND active IS TRUE)
    AND NOT EXISTS (SELECT 1 FROM hitl.identity_revocations
      WHERE tenant_id=%s AND subject=%s AND issuer=%s AND token_id=%s)
)"""

def enforce_postgres_identity(*,connection_factory,subject,tenant_id,token_id,issuer):
    """Fail closed on one atomic authority decision, not two DB connections."""
    try:
        tenant=str(UUID(str(tenant_id)))
        if (not callable(connection_factory)
            or not isinstance(subject,str) or not 8<=len(subject)<=128
            or not isinstance(issuer,str) or not issuer.startswith("https://")
            or not isinstance(token_id,str) or not 8<=len(token_id)<=256):
            raise IdentityPolicyDenied("invalid authoritative identity inputs")
        with connection_factory() as conn:
            with conn.cursor() as cur:
                cur.execute(_ATOMIC_IDENTITY,(
                    tenant,issuer,tenant,subject,issuer,
                    tenant,subject,issuer,token_id))
                row=cur.fetchone()
                if not row or row[0] is not True:
                    raise IdentityPolicyDenied("authoritative identity denied")
        return True
    except IdentityPolicyDenied:
        raise
    except Exception as exc:
        raise IdentityPolicyDenied("authoritative identity unavailable") from exc
