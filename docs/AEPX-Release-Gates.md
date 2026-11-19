# AEP-X release acceptance gates

These gates are **not complete** merely because the repository CI is green.

| Gate | Acceptance criterion | Evidence required | Current result |
|---|---|---|---|
| G1 CI and console | CI builds and console OpenAPI returns valid JSON | GitHub Actions artifact and log | Automated; new workflow pending |
| G2 Core backend | Gateway, identity, trust, registry, memory, cache and governance respond | Private Codespace smoke test log | Not verified |
| G3 Agentic workflows | Real CrewAI/MCP/RAG request succeeds; denial, timeout and HITL cases pass | End-to-end test report | Not verified |
| G4 Security | No production hard-coded secrets, externally exposed internal ports or unauthenticated privileged tools | Security review and scan | Not verified |
| G5 Resilience | Monitoring, alerts, backups and tested restoration with documented RPO/RTO | Restore and incident exercise report | Not verified |
| G6 Production release | Staged rollout, rollback, load testing and accountable approval | Signed release checklist | Not verified |

## Commands

```bash
bash scripts/codespaces.sh start
bash scripts/aepx-release-audit.sh
python3 scripts/aepx-progress.py --validate
python3 scripts/aepx-progress.py --output artifacts/aepx-progress.md
# Only in a private development Codespace:
bash scripts/codespaces.sh core
bash scripts/codespaces-smoke.sh --core
```

The `AEP-X release readiness` workflow uploads audit JSON and a milestone report as downloadable GitHub Actions artifacts. It validates the console only, not the full backend or production. Never treat the illustrative milestone percentage as a release approval.
