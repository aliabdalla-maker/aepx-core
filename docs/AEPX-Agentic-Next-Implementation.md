# Agentic AI implementation backlog after workflow guards

## Delivered in this PR
- Offline, dependency-free tool allowlist/role/timeout and approval-required contracts.
- Retrieved source-ID existence check (NOT semantic grounding or hallucination detection).
- Human approval fingerprint, expiry and consumed-state checks (NOT persistent HITL or atomic consumption).
- Unit tests and CI integration. These modules are not connected to running services.

## Required next PRs
1. **Durable HITL**: Postgres approvals, authenticated approver identity, atomic consume, audit/outbox, rejection, expiry, and replay tests.
2. **MCP gateway**: authenticated server registry, per-tool RBAC, schema validation, network isolation, deadlines, invocation audit, denial tests.
3. **RAG**: persistent ingestion and embeddings/pgvector, tenant isolation, provenance, citation validation, factual evaluation.
4. **CrewAI**: supervised agent executor, bounded retries, deterministic fixtures, budget limits, HITL integration and compensation.
5. **Observability**: OpenTelemetry, SLOs, alerts, security events, backup/restore and load tests.
6. **OCI staging**: resolve VCN quota, use approved existing network or quota increase, secret manager, TLS, restricted ingress, rollback and owner signoff.

## Production rule
No external tool side effects until the durable approval/audit and MCP authorization gates are integrated and tested. Never deploy reference development Compose publicly.
