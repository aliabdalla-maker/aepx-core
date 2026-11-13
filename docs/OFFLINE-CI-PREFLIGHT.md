# Offline CI preflight (no GitHub runner required)

From the repository root on a trusted developer workstation:

```bash
python -m pip install 'PyYAML>=6,<7'
python scripts/offline-ci-preflight.py --timeout 120 --json-output artifacts/offline-ci-preflight.json
```

This executes the workflow-integrity validator and four policy and preflight regression suites using the local Python interpreter. It exits nonzero if any check fails. It does not access OCI, deploy, merge, or run production services.

**Scope limitation:** These checks are static workflow-policy checks only. They do **not** replace MCP/PostgreSQL, HITL, durable execution, billing, Docker or OCI acceptance tests. They do not certify production readiness.

If GitHub Actions jobs remain queued, inspect runner assignment, repository Actions settings, workflow approvals, billing/spending restrictions and GitHub Status. Do not bypass required branch protection or merge without required green checks.

For the tracked remediation work, see issue #230.

The optional JSON evidence records the local Git commit, UTC timestamp, scope and per-check exit codes. Review and retain it as *partial* evidence only; it is not a GitHub required status check or a production release authorization.

Each check has a configurable timeout (default 120 seconds). Timed-out checks are marked failed with exit code 124 and `timed_out: true` in JSON evidence. A timed-out check must never be treated as a pass.

The first check compiles Python files in `scripts/` and `tests/` to detect syntax errors before executing policy tests. Compilation is a syntax check, not runtime acceptance.
