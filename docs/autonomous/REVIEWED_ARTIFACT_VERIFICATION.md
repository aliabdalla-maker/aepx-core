# Reviewed-stage artifact verification (offline)

`scripts.aepx_engineering_evidence.verify_reviewed_iteration_artifacts(state,number,root,manifest)` checks the five prerequisite stage artifacts (requirements, design, patch_proposed, tests_recorded, reviewed) **while the iteration remains reviewed**. The supplied manifest must contain exactly these five stages. Each canonical SHA-256 reference is checked against actual bytes read with descriptor-relative no-follow traversal and bounded regular-file reads.

Regression tests cover success, modified or missing bytes, extra/missing manifest entries, wrong lifecycle stage, invalid digest, symlinks and Boolean iteration identifiers.

This is a local read-time integrity check, **not an authorization to complete an iteration**. The caller-supplied ledger and manifest are not authenticated, artifacts may change after verification, and test success/reviewer identity is not established. PostgreSQL terminal completion remains disabled. A trusted completion service must bind the verification to tenant, iteration, stage, current fencing token, immutable artifact snapshot and single-use authenticated reviewer approval, then perform an atomic database transition.
