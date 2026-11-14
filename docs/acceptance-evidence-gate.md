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
