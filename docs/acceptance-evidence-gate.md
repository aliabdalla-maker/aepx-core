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

The `AEP-X 100-cycle offline acceptance` workflow is **manual-only** and
runs `tools/run_acceptance_100_iterations.py --iterations 100`. It executes
the 42-test offline integrity suite sequentially, with a 90-second timeout
per cycle, a 60-minute workflow limit, and immediate termination on the
first failure. It writes a JSON report and uploads it as a seven-day artifact.
The workflow does **not** modify code, retry known failures, execute providers,
merge pull requests, provision OCI, or deploy. A completed 100/100 result
would show repeatability of this narrow offline test suite only; it would
not establish independent security acceptance or production readiness.
