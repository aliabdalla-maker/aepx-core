# Local GitHub Actions queue triage

When GitHub-hosted workflows remain queued, run this read-only diagnostic on a local
machine instead of relying on another queued Actions workflow.

Prerequisite: GitHub CLI installed and authenticated with `gh auth login`,
with permission to read Actions metadata.

```bash
python scripts/local-actions-queue-triage.py --repo aliabdalla-maker/aepx-core --output queue-report.json
```

The report samples the latest 100 runs and includes status counts and up to
20 queued runs with their ages. It does not cancel, retry, approve, merge,
deploy, provision resources, or diagnose the underlying cause automatically.
The GitHub token is read from `gh auth token` and is never printed.
If queues persist, inspect GitHub account/organization Actions settings,
runner eligibility, billing/limits and GitHub Status, then escalate with
the report to GitHub Support. Do not infer a root cause from queued status alone.

Before using this diagnostic, run `python scripts/offline-ci-preflight.py` locally to execute its regression tests alongside workflow-policy checks. This does not replace hosted CI or validate runner availability.

The report additionally samples job runner labels and assignment for up to five queued runs (up to 20 jobs each). Missing assignments are evidence only; they do not prove an account, billing, or capacity cause. Individual job-metadata failures are recorded without discarding the run summary.

When workflow runs transition from queued to completed/failure, the report also samples up to five failed runs and records whether the Jobs API returned any jobs. A completed failure with no returned jobs warrants investigating workflow initialization, repository Actions policy and GitHub service/account state before debugging application tests. This signal alone does not identify the cause.

The report includes both `status_counts` (queued/in_progress/completed) and `conclusion_counts` (success/failure/cancelled/not_completed). Keep these separate: `completed` does not mean `success`. Check GitHub's official workflow troubleshooting documentation and validate workflow YAML before attributing missing jobs to runners.

If failed runs have no jobs, the tool now samples the Checks API for up to three failed runs. A zero check-run count, together with zero job records, is useful evidence for support but is not proof of workflow syntax or billing errors. Avoid merging or deploying until required CI gates have passed.
