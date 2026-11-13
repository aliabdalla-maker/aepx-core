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
