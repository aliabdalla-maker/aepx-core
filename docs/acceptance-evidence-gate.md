# AEP-X acceptance evidence gate

This directory contains **offline integrity checks only**, not an independent
attestation service. See `tools/verify_acceptance_evidence.py`.

## Safe use

1. Run `python -m unittest discover -s tests -p 'test_acceptance_evidence_integrity.py' -v`.
2. Collect evidence from a disposable PostgreSQL test environment with a
   non-BYPASSRLS role. Do not use production credentials or a production DB.
3. Write a JSON manifest with unique milestone IDs and positive integer weights
   totaling 100. Each milestone requires at least one relative evidence path,
   lowercase SHA-256 digest, and `result: "pass"`.
4. Run `python tools/verify_acceptance_evidence.py path/to/manifest.json`.
5. Treat `evidence_integrity_percent` only as digest verification. It can be
   forged together with its manifest and is **not** proof that tests ran.
   `independently_verified_percent` intentionally remains 0.
6. For actual release readiness, require trusted runner provenance bound to
   repository, workflow, commit SHA and immutable artifacts, plus independent
   review of security test outcomes. Do not derive independent acceptance from
   self-reported manifests.

## Mandatory release blockers

- OIDC principal-to-tenant binding and least-privilege PostgreSQL controller
- FORCE RLS, role grants, SECURITY DEFINER and concurrent replay acceptance
- Atomic approval consumption, lease fencing, terminal state and budget settlement
- Isolated worker egress, DNS rebinding and metadata endpoint denial
- Crash/retry/idempotency and duplicate billing regression
- CI required checks passing, human review and explicit deployment approval

**Do not merge or deploy on the basis of this gate alone.** No external
provider dispatch, gateway forwarding, chargeable OCI provisioning or live
production migration is authorized by this documentation.

## CI triage and evidence collection (no deployment)

- Confirm the workflow is present on the PR head and that pull_request
  path filters match the modified files. A missing run is **not** a pass.
- Open the PR Checks tab and inspect the job conclusion and individual steps.
  If no run appears, inspect repository Actions permissions, disabled workflows,
  branch protection, and event/filter behavior. Do not assume a cause.
- Collect the exact run URL, workflow name, head SHA, conclusion, timestamp,
  and immutable artifacts. Retain failed logs without copying credentials.
- The CLI contract is: exit 0 for all locally matching evidence, exit 1 for
  incomplete or mismatching evidence, and exit 2 for malformed/unreadable input.
  Even exit 0 is **not** independently attested acceptance.
- Run disposable PostgreSQL HITL/RLS acceptance using non-superuser,
  non-BYPASSRLS roles. Confirm tenant isolation, concurrent approval replay,
  lease fencing, and budget settlement with recorded failure evidence.
- Release remains blocked until trusted CI provenance, independent security
  review and explicit approval exist. Never merge/deploy automatically.

## Manifest parser safety

The parser rejects duplicate JSON keys and non-finite numeric constants, as
well as invalid milestone/evidence cardinality and ambiguous file paths.
Evidence hashing requires POSIX descriptor-based no-follow traversal and
checks file identity/size metadata before and after bounded hashing.
These checks reduce local input risks but do not authenticate who created
the evidence, establish a trusted CI run, or prove production readiness.


## CI verification handoff (mandatory before release)

1. Open the `AEP-X acceptance evidence integrity` workflow on the draft PR branch.
2. Confirm that the most recent **non-cancelled** run belongs to the intended commit SHA.
3. Require the Python preflight, all 42 discovered tests and all 14 CLI checks to pass.
4. Download the `aepx-offline-evidence-diagnostics` artifact if any step fails.
5. Record the run URL, commit SHA, workflow conclusion and reviewer identity in the release checklist.
6. Keep independent acceptance **NOT ESTABLISHED** until trusted provenance and independent review are available.

A passing offline gate is necessary for this verifier's contract but is not proof of
end-to-end AEP-X safety, PostgreSQL acceptance, HITL correctness or deployment readiness.
No merge, external provider execution, gateway forwarding or OCI provisioning is authorized by this workflow.

## Current verification boundary

The workflow's discovery floor is 42 Python tests and the workflow defines 14
CLI smoke checks. These are authored checks, not confirmed executions. A
missing or inconclusive GitHub Actions run must be reported as **unverified**,
never as passing. Do not increase maturity percentages on the basis of test
counts, local digest matches, or commits alone. Reconcile this count against
the workflow whenever tests are added or removed.

## Five-pass hardening record (2026-11-14)

1. CI summary reports missing unittest completion markers explicitly.
2. A regression rejects forged fields in later evidence entries before any hashing.
3. CI discovery minimum increased to 42 authored Python tests.
4. A thirteenth CLI smoke check rejects a forged late evidence field (exit 2).
5. This runbook and its release checklist now reflect the same counts.

These are source-level changes only. The 42 tests and 13 smoke checks must
actually execute on the PR head and their logs be reviewed. This record is not
independent attestation or authorization to merge, deploy, or spend on OCI.

## Five-pass execution-evidence hardening (second batch)

1. CI summary now requires both unittest count and outcome markers.
2. The unittest step fails unless at least 42 tests actually complete with OK.
3. A completion marker is emitted only after all CLI smoke checks pass.
4. The fourteenth CLI check rejects duplicate milestone identities.
5. This handoff is reconciled to 42 Python tests and 14 CLI checks.

All changes are authored source and workflow updates, not proof of a GitHub
runner execution. Preserve draft status, prohibit merge/deploy and keep
independent acceptance unestablished until trustworthy run evidence is reviewed.

## Manual 100-cycle offline verification

The `AEP-X 100-cycle offline acceptance` workflow can run on a scoped draft-branch push or manual dispatch and
runs `tools/run_acceptance_100_iterations.py --iterations 100`. It executes
the 42-test offline integrity suite sequentially, with a 90-second timeout
per cycle, a 55-minute runner budget within a 60-minute workflow limit, and immediate termination on the
first failure. It writes a JSON report and uploads it as a seven-day artifact.
The workflow does **not** modify code, retry known failures, execute providers,
merge pull requests, provision OCI, or deploy. A completed 100/100 result
would show repeatability of this narrow offline test suite only; it would
not establish independent security acceptance or production readiness.

### Workflow dispatch caveat

GitHub's manual workflow-dispatch UI may require the workflow definition on
the default branch. This draft branch is **not** to be merged merely to make
the manual button available. The restricted push trigger allows testing the
workflow on the draft branch without changing the default branch. Confirm a
real runner execution and inspect the uploaded report before claiming any
cycle passed.

### Incremental diagnostics and failure handling

The 100-cycle runner now atomically updates its JSON report after each
completed iteration and on global-budget exhaustion. This preserves earlier
completed cycles when a later one fails or execution is interrupted. A hard
runner termination during the currently executing subprocess can still leave
that in-flight iteration unrecorded; do not interpret the recorded count as
proof of a complete run. The workflow performs Python syntax preflight and
reports the first failed cycle in its job summary. Confirm the run and artifact
in GitHub Actions before increasing any maturity or acceptance estimates.

### Runner self-tests and interrupted-cycle reporting

The 100-cycle workflow now runs five focused runner tests before starting its
long repetition: successful cycles, fail-fast on failure, forged OK without a
test count, timeout reporting, and interrupted-cycle persistence. The runner
records an interrupted in-flight cycle as failed and returns exit code 130.
The 42 acceptance-integrity tests remain separate from these five runner tests.
Neither suite is considered passing until the actual workflow logs establish
successful execution. No automatic merge or deployment is permitted.

### Signal restoration and non-cancelling CI (latest)

The runner now restores the previous SIGTERM handler after normal completion
and after its handled interrupted-cycle return. Two additional runner self-tests
check these paths (seven runner self-tests total). The 100-cycle workflow now
triggers when the verifier or integrity tests change and queues rather than
cancels an in-progress verification. These authored checks still require real
runner execution evidence. The independent acceptance gate remains closed.

### Runner exception hardening

The runner now restores the previous SIGTERM handler through a finally block,
including unexpected exceptions. Subprocess launch and execution errors are
recorded as failed iterations with a bounded error type, rather than losing
all prior iteration results. Two new regression tests cover these cases, for
nine authored runner self-tests in total. This is not a claim of CI success.

### Regression fixture and unexpected exception correction

A runner self-test previously used literal backslash-n sequences in a simulated
unittest result instead of newline escapes. The fixture is corrected. The
runner also records unexpected exceptions as failed iterations, preserving
failure evidence and restoring the previous SIGTERM handler. This is a source
fix only; GitHub Actions execution remains to be independently confirmed.

### Terminal unittest summary enforcement

The repeated acceptance runner now requires a successful subprocess exit, at
least 42 tests, and a terminal unittest `Ran N tests ... OK` summary. An
embedded early OK followed by failure text, or a truncated summary, is rejected.
Two adversarial runner tests cover these cases (eleven runner self-tests
currently authored). A passing local repetition still does not establish
independent security acceptance.

### CI provenance and runner-test discovery

The 100-cycle workflow now requires discovery of at least twelve runner
self-tests before starting repeated acceptance verification. Reports include
the GitHub source commit SHA and workflow run ID when provided by GitHub
Actions, and the job summary displays them. One new self-test verifies these
fields. These values improve traceability but do not constitute cryptographic
attestation, independent review, or a successful test run. Release remains
blocked pending verified CI and the broader security acceptance matrix.

### Report completion and provenance gate

The 100-cycle workflow now independently checks the JSON report after the
runner finishes. It requires exactly 100 completed passing cycles, at least
42 tests per cycle, a matching GitHub commit and run ID, and explicit false
values for independent acceptance and deployment authorization. A mismatch
fails the workflow before the always-run summary/artifact steps. CI evidence
has not yet been independently observed in this conversation.

### Pull-request visibility and release checks

The 100-cycle offline acceptance workflow now runs as a pull-request check
when the runner, verifier, tests, or workflow changes. Its result is separate
from the offline evidence integrity workflow that contains the 14 CLI smoke
checks. Both results must be reviewed; neither establishes independent
security acceptance, and neither authorizes merge or deployment. A missing
workflow run or artifact is an unverified result, not a pass.

### Ordered cycle validation and stdout-spoof regression

The 100-cycle CI report gate now checks consecutive iteration IDs 1..100,
boolean passing status, integer test counts of at least 42, and zero return
codes. The runner validates unittest's terminal summary from stderr only,
rejecting a stdout-only forged success marker. Thirteen runner self-tests
are authored, including the stdout spoof regression. These source controls
still require a confirmed passing GitHub Actions run and independent review.

### No skipped or expected-failure acceptance cycles

The 100-cycle runner now requires an unqualified terminal `OK` unittest
summary. Python unittest can exit successfully while reporting skipped tests
or expected failures; these qualified outcomes are no longer counted as
acceptance passes. Two new adversarial tests cover these cases (fifteen
runner self-tests authored). This gate is still offline and does not replace
independent tenant, billing, MCP, worker, or OCI security verification.

### Durable atomic report persistence

The runner creates missing parent directories, writes JSON through a unique
same-directory temporary file, flushes and fsyncs it, then atomically replaces
the destination. Temporary files are cleaned up on failure. A new self-test
covers nested output directories and cleanup (sixteen runner tests authored).
This is a source-level safeguard, not evidence of a completed GitHub Actions
run or independent security acceptance.

### Preflight discovery and first-failure diagnostics

Before the bounded 100-cycle loop, CI now checks discovery of at least 16
runner self-tests and 42 integrity tests, and runs the runner self-tests.
The always-run job summary records the first failing cycle and a bounded
failure diagnostic when a JSON report is available. These checks do not
replace a completed workflow run or independent acceptance evidence.

### Five-pass symlink-output hardening (2026-11-14)

The acceptance runner now rejects symlinked JSON report destinations and
symlinked parent directories. Two regression tests exercise both cases,
raising the authored runner self-test count to 18; the 100-cycle workflow
requires discovery of at least 18 tests before execution. These are source
changes only; no CI result, independent acceptance, merge, or deployment is
implied. Remaining priorities: verify CI execution, collect 100-cycle report,
then independently test OIDC/RLS, HITL replay, budget settlement, MCP egress,
worker fencing and OCI staging before any release decision.

### Second five-pass output safety cycle

Report persistence now rechecks symlinked parent paths after creating
missing directories, and rejects an existing non-file destination such as a
directory. A new regression test covers the non-file target, bringing the
authored runner self-tests to 19; CI requires at least 19 discovered tests.
These changes do not establish passing CI, independent security acceptance,
or permission to merge or deploy. Review GitHub Actions results before
claiming progress beyond source hardening.

### Third five-pass CI evidence validation cycle

The 100-cycle workflow now uses explicit SystemExit-based validation rather
than Python assertions; rejects duplicate JSON keys and nonfinite JSON
constants; verifies typed sequential cycle records, bounded durations and
non-authorization flags; and attempts to preserve a useful job summary if
the report cannot be parsed. No workflow execution or independent acceptance
has been confirmed. The changes remain on a draft, non-deployed branch.

### Ten-pass standalone report-verifier implementation

Added `tools/verify_acceptance_cycle_report.py` and eight authored unit
tests in `tests/test_acceptance_cycle_report.py`. The verifier rejects
provenance mismatches, incorrect counts, missing or reordered cycles,
insufficient test coverage, nonfinite durations, duplicate JSON keys,
unauthorized deployment flags, and unestablished acceptance claims. CI now
runs the new test module and calls the verifier on the generated report.
The workflow triggers on changes to both files. Run evidence remains required;
these authored checks do not constitute independent acceptance.

### Strict report schema and bounded input checks

The standalone report verifier now enforces exact root and per-cycle field
sets, 40-character lowercase Git commit SHA and numeric workflow run ID.
It refuses symlinked evidence input paths and files larger than 2 MB. Six
new adversarial tests bring the authored report-verifier suite to 14 tests;
CI checks their discovery before execution. This is not a claim of passing
CI or independent release acceptance.

### Malformed-cycle triage and verifier coverage

The always-run CI summary now handles non-list and non-object cycle records
without crashing while reporting the first invalid entry. Four additional
adversarial tests cover boolean iteration/return-code fields, negative cycle
duration and forged independent-acceptance flags. The standalone report
verifier suite now has 18 authored tests, and CI requires discovery of all
18 before running 100 cycles. Passing workflow evidence remains outstanding.

### 60-case adversarial evidence mutation matrix

The new `tests/test_acceptance_cycle_mutations.py` runs 60 independently
named mutation scenarios (via unittest subtests) plus a valid baseline.
Each mutation must be rejected by the standalone verifier. Cases cover
unexpected root/cycle fields, wrong commit/run provenance, invalid executed
counts and invalid elapsed times. CI runs this matrix before the 100-cycle
runner. These 60 cases are authored test scenarios, not 60 successful CI
iterations, and are not independent security acceptance. The always-run
summary also handles missing count keys without raising KeyError.

### Mutation matrix completeness and CI summary confidentiality

CI now checks that the adversarial matrix contains exactly 60 unique case
names before executing it. A new test verifies that every mutation changes
the valid baseline. The always-run summary no longer republishes raw test
subprocess output, reducing the chance of accidental sensitive-data exposure
through GitHub job summaries. The report artifact itself may still contain
diagnostic output and must be handled with restricted access. No completed
CI run or independent acceptance is implied.

### Dedicated 50-cycle execution workflow

The branch includes `.github/workflows/acceptance-50-cycles.yml`.
It executes runner/verifier/mutation unit suites, requests exactly 50
sequential offline integrity cycles, verifies the resulting report with
`--expected 50` and GitHub SHA/run ID, and uploads the bounded evidence
artifact for seven days. A push to the branch affecting the configured
paths or an authorized manual dispatch can start it. CI completion is not
confirmed by creating the workflow; independent acceptance and deployment
remain blocked.

### Repeat 50-cycle execution: independent batches

The dedicated 50-cycle workflow now uses a two-entry matrix, each entry
running its own prerequisite tests, 50 sequential offline integrity cycles,
provenance verification and separately named evidence artifact. This is a
configured total of 100 cycle executions (50 + 50), not evidence of completed
runs. Both batches must pass before treating the matrix as green; it does not
replace independent acceptance or authorize deployment.

### Batch preflight and success reporting

Both 50-cycle matrix jobs now fail before execution if discovery falls below
19 runner tests, 18 report-verifier tests, 3 mutation-matrix test methods or
42 integrity tests. The matrix contains 60 mutation subtests inside its test
methods. A 50/50 success summary is written only after the report verifier
returns successfully. Neither configured execution nor an authored summary
is proof of a completed GitHub Actions run. Preserve the release block until
actual CI artifacts and independent security acceptance have been reviewed.
