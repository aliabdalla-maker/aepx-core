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
