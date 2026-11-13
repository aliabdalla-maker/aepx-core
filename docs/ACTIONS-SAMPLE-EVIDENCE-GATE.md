# Actions sample evidence gate

After generating a local triage report, evaluate the sampled run conclusions:

```bash
python scripts/local-actions-queue-triage.py --repo aliabdalla-maker/aepx-core --output actions-triage.json
python scripts/actions-sample-gate.py actions-triage.json
```

Exit 1 means failed, cancelled, queued, incomplete, or inconsistent evidence.
Exit 2 means the evidence file could not be read or parsed. Exit 0 only
indicates that the **sample** contains at least one success and no failed
or unfinished runs. It **does not** prove that required workflow gates ran,
that the SHA is correct, or that production deployment is authorized.
Mandatory release acceptance and explicit human approval remain required.

The validator also requires a consistent `status_counts` object with every sampled run marked `completed`. Unrecognized conclusion values, status values, or inconsistent totals block acceptance. This is a sampled diagnostics gate, not a substitute for named mandatory checks on the exact release SHA.

## Exact-SHA mandatory workflow mode

The triage JSON now includes run-level SHA, workflow path, status and conclusion. To check mandatory workflows for a target commit, run:

```bash
python scripts/actions-sample-gate.py actions-triage.json --sha FULL_40_CHARACTER_COMMIT_SHA --require-workflow .github/workflows/aepx-core-gates.yml --require-workflow .github/workflows/aepx-release-readiness.yml
```

Replace workflow paths with the **actual required files** in your repository; do not assume the example release-readiness filename exists. A missing, queued, failed or wrong-SHA workflow blocks. The API sample is limited to the latest 100 runs, so older successes may be absent; absence must be treated as unverified, not failed code. This check does not replace security acceptance or manual release approval.

For exact-SHA mode, the newest matching run in the triage report must be completed and successful. A newer failed or queued rerun overrides an older success. Triage results are ordered newest first by GitHub's run listing; do not reorder them before evaluation.

Run-order metadata is validated before comparison: positive integer IDs and attempts, parseable timezone-aware timestamps, and chronological ordering across UTC offsets. Invalid or missing metadata blocks exact-SHA acceptance.
