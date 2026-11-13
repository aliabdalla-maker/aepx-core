"""Fail-closed identity and approval recheck immediately before external dispatch.

This is a pure authorization gate. It performs no external effects and must
be called by the actual fenced worker immediately before effect execution.
"""
from .hitl_identity_policy import IdentityPolicyDenied
from .hitl_identity_postgres import enforce_postgres_identity

class DispatchDenied(PermissionError):
    pass

def authorize_hitl_dispatch(*, connection_factory, subject, tenant_id, token_id,
                            issuer, approval_id, lease_token, task_id,
                            verify_approval, verify_lease, verify_task):
    """Require literal True from three trusted checks plus live identity DB.

    Callbacks MUST use authoritative persistent state and bind every lookup to
    tenant, task, approval and lease. A separate atomic consume/dispatch
    transaction remains necessary to prevent a post-check race.
    """
    try:
        if (not isinstance(approval_id,str) or not approval_id.strip()
            or not isinstance(lease_token,str) or not lease_token.strip()
            or not isinstance(task_id,str) or not task_id.strip()
            or not all(callable(c) for c in
                       (verify_approval,verify_lease,verify_task))):
            raise DispatchDenied("invalid dispatch authorization inputs")
        enforce_postgres_identity(
            connection_factory=connection_factory,subject=subject,
            tenant_id=tenant_id,token_id=token_id,issuer=issuer)
        scope=dict(tenant_id=tenant_id,task_id=task_id,
                   approval_id=approval_id,lease_token=lease_token)
        if verify_task(**scope) is not True:
            raise DispatchDenied("task authorization denied")
        if verify_lease(**scope) is not True:
            raise DispatchDenied("fenced lease denied")
        if verify_approval(**scope) is not True:
            raise DispatchDenied("HITL approval denied")
        return True
    except DispatchDenied:
        raise
    except Exception as exc:
        raise DispatchDenied("pre-dispatch authorization unavailable") from exc
