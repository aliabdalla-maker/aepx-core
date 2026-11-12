# Phase 2.1 — guarded execution integration (draft)

## Implemented
- Worker core claims an **approved** run with a row lock, max two attempts, and status transitions; never runs by default.
- Provider SDK adapters: OpenAI Responses, Anthropic Messages, Gemini Generate Content and OCI Generative AI Inference (credentials and model identifiers supplied only by server environment).
- Explicit CrewAI LLM construction, text-only agents and no agent tools; no silent default provider.
- MCP Streamable HTTP client with HTTPS endpoint allowlist, service bearer token and exact per-tool allowlist; external calls disabled by default.
- pgvector extension, tenant-filtered 1536-dimensional chunk storage and OpenAI embedding/search adapter, disabled by default.
- Run audit, cancellation, retry and a Next.js agent dashboard.
- Integration tests and migration in dedicated CI.

## Critical limitations and security gates
**This is not a production-ready autonomous worker.** No worker scheduler, queue, distributed lease recovery, runtime sandbox, enforced wall-clock kill, verified DNS/IP egress filtering, model-spend metering, per-tenant credential vault, or comprehensive tool-argument approval is implemented. A running model request cannot be forcibly interrupted by the cancellation endpoint; cancellation prevents its result being saved. MCP URL checks do not stop DNS rebinding, so use a dedicated egress proxy with strict DNS/IP allowlisting before enabling MCP. Do not enable external execution on a publicly reachable instance.

The dashboard submits tasks and human decisions. Approval changes status; the API **never starts the worker**. A separately operated worker process must invoke `execute_one` with a trusted tenant and run identifier. No worker process or deployment is configured here.

## Database
Apply `001_phase1.sql`, `002_phase2.sql`, then `003_phase21.sql` as a privileged migration role. PostgreSQL must have the pgvector extension installed. Use a separate least-privileged runtime role, without table ownership or BYPASSRLS. Grant `SELECT,INSERT` on `ide_agent_audit`, `SELECT,INSERT,DELETE` on `ide_knowledge_vectors`, and `SELECT,INSERT,UPDATE` on `ide_agent_runs`.

## Provider configuration
Install `backend/requirements-agent.txt` only on an isolated worker image. `IDE_EXTERNAL_EXECUTION_ENABLED` must remain unset or false until reviewed. Configure explicit provider model IDs: `IDE_OPENAI_MODEL`, `IDE_ANTHROPIC_MODEL`, `IDE_GEMINI_MODEL`, `IDE_OCI_MODEL`, along with `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` or OCI SDK config, compartment and endpoint. The `IDE_LLM_*_ENABLED` flags select available routes but do not validate credentials.

MCP configuration: `IDE_MCP_KNOWLEDGE_URL`, `IDE_MCP_KNOWLEDGE_TOKEN`, `IDE_MCP_KNOWLEDGE_TOOLS` and corresponding `IDE_MCP_GITHUB_READONLY_*`. Explicitly enabling `IDE_MCP_EXECUTION_ENABLED` alone is insufficient; the global external execution flag is also required.

Vector RAG requires `IDE_RAG_EMBEDDING_ENABLED=true`, global execution flag, `OPENAI_API_KEY` and a compatible 1536-dimensional embedding model. Text-only lexical search remains available without embeddings.

## Required before production
1. Replace manual worker invocation with a durable queue, per-tenant concurrency, leases and idempotency.
2. Enforce actual model spending and hard timeouts in a sandboxed worker with network egress controls.
3. Add audited approval of exact MCP tool names and arguments, not just an allowlist.
4. Verify provider SDK compatibility with real credentials in an isolated staging environment.
5. Perform browser OIDC, RLS, adversarial prompt-injection, cancellation and concurrency end-to-end tests.
6. Keep draft PR unmerged and OCI undeployed.
