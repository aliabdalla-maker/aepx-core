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
3. Require the Python preflight, all 35 discovered tests and all 12 CLI checks to pass.
4. Download the `aepx-offline-evidence-diagnostics` artifact if any step fails.
5. Record the run URL, commit SHA, workflow conclusion and reviewer identity in the release checklist.
6. Keep independent acceptance **NOT ESTABLISHED** until trusted provenance and independent review are available.

A passing offline gate is necessary for this verifier's contract but is not proof of
end-to-end AEP-X safety, PostgreSQL acceptance, HITL correctness or deployment readiness.
No merge, external provider execution, gateway forwarding or OCI provisioning is authorized by this workflow.
