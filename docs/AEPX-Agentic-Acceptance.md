# AEP-X Agentic Acceptance: staged validation

This PR introduces **negative-path probes against existing endpoints**, not a CrewAI/MCP/RAG/HITL production implementation.

## Private Codespace (non-destructive)
Start the full required dependencies only if adequate resources are available. Existing `codespaces.sh core` starts governance but **does not start workflow or knowledge**. Those services depend on Kafka and/or PostgreSQL and must be explicitly started before the agentic probe.

```bash
bash scripts/codespaces.sh start
bash scripts/codespaces.sh core
docker compose -f docker-compose.yml -f compose.codespaces-core.yml up -d --build kafka workflow knowledge
python3 scripts/aepx-agentic-acceptance.py
```

The checks cover S0 allowed, S4 denied, invalid risk denied, empty retrieval for a deliberately absent token, and missing-workflow rejection. They do not mutate business data or invoke external tools.

## Known expected failure
The current workflow endpoint directly indexes its in-memory dictionary for unknown IDs; FastAPI may return HTTP 500 instead of 404. The probe deliberately fails until this is corrected. In-memory workflow and knowledge stores also do not survive restarts.

## Remaining work (not claimed as delivered)
- CrewAI supervisor/worker orchestration with bounded retries and structured outputs.
- MCP authenticated tool discovery, allowlist, timeout, denial audit, and human approvals.
- Persistent RAG vector indexing, source provenance and citation verification.
- Durable HITL approval, denial, idempotency, and rollback before irreversible actions.
- Service-level tracing, alerts, backups and isolated restore drill.
- Secure OCI staging, quotas/network, release approval and rollback.

Do not expose development Compose services to the public internet.
