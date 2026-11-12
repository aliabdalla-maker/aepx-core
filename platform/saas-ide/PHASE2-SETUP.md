# Phase 2 — Governed AEP-X supervisor (draft)

## Delivered
- OIDC-authenticated, PostgreSQL-tenant-scoped agent task submissions and durable plans.
- Explicit owner/admin HITL approval and rejection; editor can request but not approve.
- Configurable provider selection for OCI, OpenAI, Anthropic and Gemini. Provider availability is a **configuration flag**, not a tested model connection.
- Tenant-scoped knowledge document storage and lexical retrieval with excerpts. This is **RAG groundwork**, not vector/embedding RAG.
- CrewAI text-only adapter and MCP tool discovery adapter behind server-side opt-in/allowlist. They are **not wired into the request execution path**.
- No autonomous code execution, MCP tool invocation, model inference, GitHub writes or OCI deployment.

## Setup
Apply `backend/migrations/002_phase2.sql` using the privileged migration role after Phase 1.
Grant the runtime role `SELECT, INSERT, UPDATE` on `ide_agent_runs` and `SELECT, INSERT` on `ide_knowledge_documents`. Do not grant table ownership or BYPASSRLS.

Provider flags: `IDE_LLM_OCI_ENABLED`, `IDE_LLM_OPENAI_ENABLED`, `IDE_LLM_ANTHROPIC_ENABLED`, `IDE_LLM_GEMINI_ENABLED` (literal `true`); `IDE_LLM_PRIORITY` defaults to `oci,openai,anthropic,gemini`. Flags only control planning routes; set them only when approved credentials, quotas and endpoints are configured.

`POST /api/v1/agent-runs` accepts `{"project_id":"...","task":"...","preferred_provider":"oci"}`.
`POST /api/v1/agent-runs/{id}/decision?approved=true` requires owner/admin; **approval changes status only**.
`GET /api/v1/agent-runs/{id}` returns the current plan/status.
`POST /api/v1/projects/{id}/knowledge` stores a document; `POST /api/v1/projects/{id}/knowledge/search` retrieves lexical matches.

## Release blockers
1. Run Python unit and PostgreSQL integration tests; test all roles and cross-tenant RLS.
2. Integrate a sandboxed worker with idempotency, cancellation, budget limits and audit logs.
3. Wire CrewAI with explicit provider-specific LLM objects and enforce tenant-scoped credentials.
4. Add real embeddings/pgvector, chunking and retrieval evaluation.
5. Add secure MCP endpoint authentication, DNS/SSRF controls, per-tool allowlists and approval of tool arguments.
6. Add browser agent dashboard and secure execution approvals.
7. No deployment or merge until these are verified.
