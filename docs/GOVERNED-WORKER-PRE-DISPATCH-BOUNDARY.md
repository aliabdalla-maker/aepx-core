# Governed worker dispatch authorization boundary

The worker now refuses externally enabled execution unless a trusted
`authorize_dispatch` callback is supplied. After the fenced job claim,
budget reservation and fresh lease/status read, the callback receives
`tenant_id`, `job_id`, `run_id`, `owner` and `fencing_token`.
Only literal `True` permits the provider call. All other results or
exceptions fail closed.

**Not yet a complete HITL integration.** The production composition
root must implement this callback by resolving the task's identity,
token, issuer and exact approval, invoking the authoritative
`hitl_pre_dispatch_gate` and binding the decision to the same fenced
lease. A callback that merely returns True is insecure. The current
worker cannot prove an injected callback's trustworthiness.

For irreversible actions, identity/approval consumption and fenced
dispatch must be atomic or coordinated through a durable transactional
outbox with downstream idempotency. Recheck immediately at the effect
boundary; never infer exactly-once execution from a preflight decision.

External execution remains disabled by default. No credentials,
deployment, OCI resources or live database migrations are added.
