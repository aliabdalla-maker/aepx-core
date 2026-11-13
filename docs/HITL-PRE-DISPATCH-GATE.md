# Pre-dispatch HITL identity gate

The new pure gate checks authoritative PostgreSQL membership/revocation,
trusted task authorization, fenced lease and exact HITL approval.
Each callback must return literal `True`. Exceptions deny.

This gate **does not yet connect to the production worker** and does not
perform or authorize external effects by itself. Its callback contracts
are not a substitute for binding approval consumption and the fenced
dispatch operation in an atomic transaction. The worker integration must
enforce that no effect can execute on a stale approval or lease, including
revocations committed between preflight and dispatch.

CI status: workflow runs have remained queued. Diagnose repository
Actions permissions, runner availability, concurrency restrictions and
billing/usage limits before interpreting tests as passing. Do not
deploy or enable external effects without verified integration acceptance.
