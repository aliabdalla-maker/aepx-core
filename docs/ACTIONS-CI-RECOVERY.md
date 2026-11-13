# AEP-X GitHub Actions CI recovery — fail-closed procedure

## Observed evidence (2026-11-13)
The latest sampled 30 Actions runs were completed with failure. One inspected
core-integration run returned zero jobs. A sampled failed release-readiness
commit returned zero check runs. These observations do **not** prove whether
the cause is invalid workflow YAML, account limits, permissions, or service
availability. Production release remains blocked.

## 1. Collect read-only evidence outside Actions
From an authenticated workstation or OCI Cloud Shell (no provisioning):
```bash
gh auth status
python scripts/offline-ci-preflight.py --json-output offline-preflight.json
python scripts/local-actions-queue-triage.py --repo aliabdalla-maker/aepx-core --output actions-triage.json
gh run list -R aliabdalla-maker/aepx-core --limit 30
gh run view RUN_ID -R aliabdalla-maker/aepx-core
```
Never paste tokens or secrets into reports. If a run has no jobs or logs, retain
its URL, SHA, timestamps and API evidence rather than claiming tests failed.

## 2. Validate workflow files before changing Actions settings
Inspect the workflow error banner in GitHub Actions. Use the repository's
offline workflow integrity checker and, if available, an independent
`actionlint` installation:
```bash
python scripts/check_workflow_integrity.py
actionlint -color
```
Fix only demonstrated syntax/schema/expression errors in a reviewed PR.
Do not bulk-rewrite deployment workflows. A YAML parse pass alone is not
equivalent to full GitHub Actions schema validation.

## 3. Review account and repository configuration
With an authorized repository administrator, inspect repository Settings →
Actions → General for Actions enablement, allowed actions and runner policy.
Review account/organization Actions usage, billing, storage and budget status;
check GitHub Status for incidents. Do not change budgets, enable paid usage,
or relax security policies without explicit authorization.

## 4. Recovery acceptance
- At least one minimal read-only workflow starts and produces job/step logs.
- The workflow-policy and core integration gates pass on the target SHA.
- Required PostgreSQL, HITL, MCP, egress, crash-recovery and billing tests pass.
- Evidence references exact run URLs, SHA, test results and environment.
- Manual-only deployment, no-cost OCI constraints and approval gates remain intact.

## 5. Escalation
If runs continue to fail before jobs after workflow validity and account
settings have been checked, open a GitHub Support case with the redacted
triage report, affected run URLs, timestamps, repo, commit SHA, and a precise
description of missing jobs/checks. Do not assert a root cause without evidence.


## Stuck-run support escalation (13 November 2026)

GitHub's 9 November Actions/Checks incident postmortem acknowledges that some jobs remained stuck and reduced available concurrency after mitigation. This is a **hypothesis**, not a confirmed diagnosis for this repository. See https://www.githubstatus.com/ and https://docs.github.com/en/actions/how-tos/troubleshoot-workflows .

1. Preserve read-only evidence locally: `python scripts/local-actions-queue-triage.py --repo aliabdalla-maker/aepx-core --output actions-triage.json`. Treat the resulting JSON as internal diagnostic data; inspect before sharing externally.
2. For each oldest stuck run, record run ID, URL, workflow path, commit SHA, created/updated times, run status, job count, check-run count and any concurrency group in the workflow YAML. Record whether the run is using GitHub-hosted or self-hosted runners.
3. Inspect repository Settings > Actions > General (permissions, allowed actions and runners), account Actions usage/billing, and GitHub Status. Check YAML validity independently using `actionlint` on a trusted local checkout. Do not change settings or trigger mass reruns merely to test a hypothesis.
4. If authorized by the repository owner, attempt normal cancellation of **one** confirmed obsolete stuck run; document the result. Do not bulk-cancel or force-cancel production-critical runs.
5. If cancellation fails, or a queued run has no jobs and blocks later runs, contact GitHub Support with the read-only evidence. GitHub's troubleshooting guide explicitly warns that self-service cancellation may not clear out-of-sync check suites.
6. After recovery, require successful mandatory checks on the exact candidate SHA, plus tenant isolation, HITL, billing/recovery and OCI staging acceptance. A green diagnostic sample alone never authorizes release.

Support case summary: "Repository aliabdalla-maker/aepx-core has repeated queued/pending Actions runs with missing or nonstarting jobs. Please inspect check-suite state, concurrency locks and runner assignment, and whether stuck runs from the November 9 incident affect this repository. We have not established the root cause. Run IDs and JSON diagnostics are attached."

**Safety:** Do not disable required checks, weaken branch protection, merge pending changes, enable external execution, or provision chargeable OCI resources as a workaround.
