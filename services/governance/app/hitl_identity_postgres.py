"""Authoritative tenant membership and JWT revocation checks using PostgreSQL.

The connection factory must use a restricted, non-owner identity-read role.
The database must be maintained by an independent trusted identity service.
"""
from uuid import UUID
from .hitl_identity_policy import enforce_identity_policy,IdentityPolicyDenied

def postgres_identity_verifiers(connection_factory):
    if not callable(connection_factory):
        raise IdentityPolicyDenied("trusted identity connection required")

    def membership(*,subject,tenant_id,issuer):
        try:
            tenant=str(UUID(str(tenant_id)))
            with connection_factory() as conn:
                with conn.cursor() as cur:
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
                    cur.execute("""SELECT EXISTS(
                        SELECT 1 FROM hitl.identity_revocations
                        WHERE tenant_id=%s AND subject=%s AND issuer=%s
                          AND token_id=%s)""",(tenant,subject,issuer,token_id))
                    row=cur.fetchone()
                    return bool(row and row[0] is False)
        except Exception:
            return False
    return membership,not_revoked

def enforce_postgres_identity(*,connection_factory,subject,tenant_id,token_id,issuer):
    membership,not_revoked=postgres_identity_verifiers(connection_factory)
    return enforce_identity_policy(subject=subject,tenant_id=tenant_id,
        token_id=token_id,issuer=issuer,verify_membership=membership,
        verify_not_revoked=not_revoked)
