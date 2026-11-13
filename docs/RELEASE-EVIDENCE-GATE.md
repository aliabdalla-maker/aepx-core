# Release evidence gate

Before any OCI staging promotion or production rollout, require green **push**
runs for both **CI** and **HITL P0 acceptance** on the **exact target commit**.
A passing PR check on another SHA, a queued job or a missing workflow is not
release evidence.

Run from an authenticated GitHub CLI environment:

```bash
SHA="$(git rev-parse HEAD)"
python scripts/verify_release_evidence.py --repo aliabdalla-maker/aepx-core --sha "$SHA"
```

Exit codes: 0 = verified, 1 = missing/failing/queued evidence, 2 = GitHub
API unavailable or invalid response. The verifier is read-only and never
starts workflows, merges changes, handles secrets or deploys infrastructure.

## Next operational steps

1. Check Settings → Actions → General for workflow permissions and restrictions.
2. Check Settings → Actions → Runners for usable hosted/self-hosted runners.
3. Check billing, spending limits and any organization policy restrictions.
4. Re-run CI and HITL acceptance on the exact target commit.
5. Review all failures and security findings; merge only after approval.
6. Run disposable PostgreSQL acceptance and the 100-pass sequential suite.
7. Complete authenticated MCP provider sandbox, CrewAI/RAG and OCI recovery gates.

This check does not replace provider verification or deployment approval.

## Exact-SHA workflow trigger invariant

The HITL acceptance workflow must run on every push, including documentation,
release tooling and workflow-only commits. Path filtering can cause a missing
HITL run and make the mandatory exact-SHA release gate unsatisfiable. The
workflow also accepts pull requests and manual dispatch for diagnostics, but
**only successful push runs** count as release evidence. A queued run remains
a blocker; this change does not provision or fix GitHub runners.
