# Sequential 1,000-pass HITL acceptance

Manual GitHub Actions workflow: `.github/workflows/hitl-sequential-1000.yml`.

It executes **ten non-overlapping jobs** (`max-parallel: 1`), each running
100 offline HITL test passes in a single process. A failed pass stops its batch;
`fail-fast: true` cancels subsequent scheduled batches when a job fails.
The order of numbered matrix batches is not guaranteed; they are serial, not
necessarily numbered 1 through 10 in scheduling order.

Each batch uploads a JSONL report. An operator must inspect all ten artifacts
and count exactly 1,000 successful records before claiming completion. The
workflow itself does not aggregate, independently certify or attest all records.

**Scope:** This is test repetition, not 1,000 development/repair iterations.
It makes no code edits, PRs, merges, cloud changes, or external provider calls.
CI runners and GitHub-hosted job quotas must be available. A queued job means
zero verified passes, regardless of workflow configuration.

Next: restore runners; validate full PostgreSQL suite and trusted identity
integration; sandbox MCP tools; governed CrewAI/RAG; OCI staging and rollback.
