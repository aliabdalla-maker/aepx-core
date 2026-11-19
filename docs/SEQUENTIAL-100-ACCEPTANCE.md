# AEP-X: 100 sequential acceptance passes

This is a repeatable **test-and-report** workflow, not an autonomous software
engineer. It does not invent fixes, alter code, merge PRs, call MCP providers
or deploy OCI infrastructure.

1. Review and merge the draft workflow after CI/security review.
2. In GitHub Actions, select **Sequential 100-pass HITL acceptance**,
   choose **Run workflow** and **100** passes.
3. Each iteration waits for the previous pytest invocation to finish.
4. The first failure stops the run and retains a JSONL report artifact.
5. Investigate the failing test, fix it in a separate reviewed PR, then rerun.
6. After the 100 passes succeed, run the independent PostgreSQL acceptance,
   provider sandbox, identity, RAG and OCI staging gates.

**Current blockers:** GitHub-hosted jobs have remained queued; this workflow
cannot fix runner availability. A successful 100-pass offline run does not
prove PostgreSQL, remote provider, CrewAI/RAG or OCI production readiness.
