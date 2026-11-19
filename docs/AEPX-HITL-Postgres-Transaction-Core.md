# PostgreSQL HITL transaction core

`services/governance/app/hitl_postgres.py` introduces an **unwired** transactional core for a future authenticated service. It atomically locks and consumes an approved action, writes an audit event and inserts an outbox event using one PostgreSQL transaction. All SQL is parameterised; the tenant session setting is transaction-local. The caller must provide authenticated and authorised tenant/actor identities.

## Test
```bash
python3 -m unittest discover -s tests -p 'test_aepx_hitl_postgres.py' -v
```

These are **mock-based contract tests**, not database integration tests. No OCI tenancy or database was changed.

## Mandatory work before enabling
1. Implement trusted identity verification, role separation, approval request/decision endpoints, and tenant membership validation. Never accept caller-provided tenant/approver identity as proof.
2. Introduce non-owner runtime DB roles, grants, transaction-local tenant settings, RLS tests with two real tenants, and apply migrations with a reviewed migration runner.
3. Add outbox dispatch workers with bounded retries, idempotent consumers, dead-letter handling and reconciliation. Atomic DB event creation is **not** exactly-once external execution.
4. Add integration tests against PostgreSQL with concurrent consumes, expired/rejected approvals, crash recovery and forced rollback.
5. Wire MCP execution through HITL with strict schema validation, network isolation and operator approvals. Keep consequential tools disabled until all checks pass.
6. Review OCI Always Free resource use, credentials, backups, monitoring and network restrictions before staging deployment.
