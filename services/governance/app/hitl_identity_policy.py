"""Independent trusted tenant membership and revocation checks.

Callbacks must query authoritative systems, not claims from the JWT itself.
No network calls or database writes are performed by this policy.
"""
from uuid import UUID

class IdentityPolicyDenied(PermissionError):
    pass

def enforce_identity_policy(*,subject,tenant_id,token_id,issuer,
                            verify_membership=None,verify_not_revoked=None):
    """Fail closed unless BOTH trusted decisions return literal True."""
    try:
        tenant=str(UUID(str(tenant_id)))
        if (not isinstance(subject,str) or not 8<=len(subject)<=128
            or not isinstance(issuer,str) or not issuer.startswith("https://")
            or not isinstance(token_id,str) or not 8<=len(token_id)<=256):
            raise IdentityPolicyDenied("invalid identity policy inputs")
        if not callable(verify_membership) or not callable(verify_not_revoked):
            raise IdentityPolicyDenied("authoritative identity checks required")
        if verify_membership(subject=subject,tenant_id=tenant,issuer=issuer) is not True:
            raise IdentityPolicyDenied("tenant membership not confirmed")
        if verify_not_revoked(subject=subject,tenant_id=tenant,issuer=issuer,
                              token_id=token_id) is not True:
            raise IdentityPolicyDenied("token revocation status not confirmed")
        return True
    except IdentityPolicyDenied:
        raise
    except Exception as exc:
        raise IdentityPolicyDenied("identity policy check unavailable") from exc
