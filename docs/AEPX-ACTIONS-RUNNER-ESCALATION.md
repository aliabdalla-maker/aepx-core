# AEP-X GitHub Actions runner escalation — 2026-11-14

## Observed evidence (not a root-cause diagnosis)

- Main CI workflow run: https://github.com/aliabdalla-maker/aepx-core/actions/runs/43559233437
- Commit reported for that run: `4f0545650c9e2ee842887951048d2ab0da1bc2c3`
- GitHub Actions jobs API reports **37 jobs** for this run.
- Sampled jobs `catalogue`, `contracts`, and `test-soa (console)` are **queued**, request `ubuntu-latest`, and have `runner_id: null`.
- Other recent HITL/PostgreSQL workflow runs were also observed queued.
- This evidence does **not** establish billing, policy, runner-capacity, concurrency, or GitHub incident as the cause.

## Owner checks (GitHub web UI; do not change settings without approval)

1. Open **Settings → Actions → General**. Check Actions enabled, allowed actions, workflow permissions, and whether approval is required for the run's event.
2. Open **Settings → Actions → Runners** where available. Check hosted-runner eligibility and any runner-group restrictions. The sampled jobs request `ubuntu-latest`.
3. Review account/organization **Billing & licensing → Actions** usage, spending limits and any restrictions. Do not add payment methods or increase spend limits without approval.
4. Review https://www.githubstatus.com/ for a relevant Actions incident.
5. Open the affected run and individual queued jobs; capture queue messages, timestamps and any required-approval banners.
6. If unresolved, open a GitHub Support ticket with the run URL, run ID, job ID, `ubuntu-latest` label, `runner_id: null`, and UTC timestamps. Do not include access tokens or secrets.

## Safe diagnostic execution

The read-only script `scripts/actions-queue-inspector.py` can be run in an available trusted environment with an Actions **read-only** GitHub token. Do not paste the token into logs or issues. The script reports a limited recent-run sample and does not establish the root cause.

## Acceptance gates after runner availability returns

1. Run offline queue-inspector and exact-SHA evidence regression tests.
2. Run the main CI matrix on the current protected `master` SHA.
3. Run disposable PostgreSQL MCP/RLS acceptance and HITL authorization, identity, replay and receipt suites.
4. Run fenced-lease recovery, budget settlement, duplicate-billing and network-egress regressions.
5. Run Docker/release readiness checks; collect immutable run IDs, SHA and artifact links.
6. Keep `release_approved: false` until every required gate has verified successful evidence and an authorized human approves release.

**Safety:** no automatic merges, deployments, paid OCI resources, secrets disclosure or billing changes.
