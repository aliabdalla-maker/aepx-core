# AEP-X core integration and production gate runbook

## Scope
The private Codespace is the development environment. CI validates static checks; it does **not** run the entire backend, external LLMs, MCP tool calls or OCI production infrastructure.

## Private Codespace execution
```bash
git switch master
git pull --ff-only origin master
bash scripts/aepx-dev-acceptance.sh --core
```
This starts the console, executes the release audit, starts the core services and performs read-only HTTP OpenAPI checks against gateway, identity, trust, registry, memory, cache and governance. Results: `artifacts/aepx-core-integration.json`, `artifacts/aepx-release-audit.json` and `artifacts/aepx-progress.md`.

## Production security gate
```bash
python3 scripts/aepx-static-security.py --production-gate
```
**Expected to fail currently:** the reference Compose contains development credentials and published ports. This is deliberate fail-closed behavior, not a false green production approval. Do not publish this stack on public interfaces.

## Outstanding integration acceptance
- CrewAI multi-agent task with deterministic success and failure cases.
- MCP tool permissions, denial paths, timeout handling and audited invocation.
- RAG ingestion, retrieval provenance, grounded answers and hallucination tests.
- Human approval for irreversible actions, idempotency and rollback tests.
- Production secrets, TLS, RBAC, service-to-service authentication and vulnerability scans.
- Metrics/alerts, persistent volumes, scheduled backups, restore drill, RPO/RTO and OCI quotas.
- Staging load test, rollback rehearsal and release owner signoff.

## Operator troubleshooting
Run `bash scripts/codespaces.sh core-status`, `bash scripts/codespaces.sh core-logs` and inspect the JSON report for failed HTTP probes. Do not share tokens, passwords or raw environment dumps. The reference Compose may require more resources than a small Codespace.
