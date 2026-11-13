# AEP-X local HITL persistence foundation

This change adds a **local SQLite prototype** for approval state transitions, not a networked production HITL service. It has transactionally recorded requested/approved/rejected/consumed events, action-hash binding, expiry, separation of requester and approver, and one-time consumption.

## Test
```bash
python3 -m unittest discover -s tests -p 'test_aepx_hitl_store.py' -v
```

## Critical limitations
- Caller-supplied requester and approver identities are **not authenticated**. Never expose the module as a public approval API.
- SQLite storage is local; production requires PostgreSQL, backups, migration, tenant isolation, RBAC and auditable identities.
- Consuming approval and performing an external side effect are not one atomic operation; production requires a durable outbox/idempotency design and reconciliation.
- Audit events are transactional but **not immutable or cryptographically anchored**.
- This prototype is not connected to CrewAI, MCP, RAG or the workflow service.
- Production remains blocked by reference Compose credentials, exposed ports and OCI network quota.

## Next engineering sequence
1. Replace local approval storage with PostgreSQL and authenticated approver identity.
2. Implement a durable transactional outbox and idempotency keys.
3. Add MCP gateway tool allowlists, schema validation, deadlines, network isolation and audit.
4. Add tenant-scoped RAG ingestion, vector search, citations and factuality evaluation.
5. Wire CrewAI supervisor to MCP through HITL, with deterministic integration fixtures.
6. Add OpenTelemetry, SLOs, restore drill, encrypted backups and rollback.
7. Deploy to restricted OCI staging after VCN quota/network resolution; never use reference Compose for production.

## Additional local outbox prototype
`scripts/aepx-local-outbox.py` provides SQLite-backed idempotent enqueue, pending event inspection and delivery marking, with tests. It does not send events, authenticate producers, or atomically combine HITL consumption with external side effects. It must not be treated as exactly-once delivery or a production event bus.
