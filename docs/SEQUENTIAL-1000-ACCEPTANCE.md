# Sequential 1,000-pass HITL acceptance

The manually dispatched GitHub Actions workflow runs **one job** executing
`scripts/sequential_acceptance_1000.py`. The orchestrator executes ten
100-pass batches **in numeric order**, waiting for each to finish before the
next starts. Every batch is validated against exactly 100 JSONL pass records.
A missing, malformed, failed or incomplete batch stops the process.

Each run must use a fresh report directory. The workflow uploads all ten
batch artifacts plus `summary.jsonl`. A completed job and 1,000 verified
records are required before claiming acceptance; a queued workflow proves
nothing. The GitHub-hosted job has a six-hour limit; a timeout is a failure.

This is repeated **offline testing**, not 1,000 software-development cycles.
It does not modify source, create PRs, invoke external providers or deploy.
The workflow must be merged and manually dispatched; no execution is implied
by committing it.

## Remaining blockers

Restore GitHub Actions runners; verify PostgreSQL integration tests and
OIDC/RBAC operator identity; implement provider-side MCP evidence verification;
govern CrewAI/RAG tool actions; validate monitoring, OCI staging and rollback.
