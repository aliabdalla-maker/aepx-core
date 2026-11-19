# GitHub Actions queue diagnosis

For the exact target SHA, with authenticated `gh` CLI:

```bash
python scripts/diagnose_actions_queue.py --repo aliabdalla-maker/aepx-core --sha "$(git rev-parse HEAD)"
```

This read-only script reports queued jobs and queue age. Exit code 1 indicates
a stale queue (default threshold 15 minutes), 2 means status could not be
verified, and 0 means no stale queued jobs were detected. **Exit 0 is not a
passing CI result**; the separate exact-SHA release evidence gate is mandatory.

If queued, inspect repository Settings → Actions → General, Actions → Runners,
organization Actions policy, billing limits, GitHub service status and
workflow concurrency. Do not bypass the gate, claim test success, or deploy.

After runners are available, run the mandatory HITL/PostgreSQL acceptance,
then manually dispatch the sequential 1,000-pass workflow. Confirm all
1,000 JSONL records and the complete workflow conclusion.
