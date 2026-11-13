# PR #35 — Scoped credential release gate

The `staging.sh --start` path now rejects deployments unless `AEPX_REQUIRE_SCOPED_KEYS=true` and the three separate credentials (`AEPX_REGISTRY_IDENTITY_KEY`, `AEPX_REGISTRY_WRITE_KEY`, `AEPX_TRUST_WRITE_KEY`) are configured, at least 32 characters each and mutually distinct. The validation reads the local `.env` without sourcing it as shell code; exported environment variables take precedence. It runs before any Compose startup. `--validate` remains non-mutating and does not require scoped secrets, so operators can inspect a draft configuration.

This change does not establish a production-ready deployment. Before lifting draft status: confirm all CI jobs pass, test ARM64 image availability and actual OCI shape, verify a non-production host and Always Free quotas, prove encrypted backup restoration, perform PostgreSQL RLS integration testing, validate external HTTPS and OIDC authentication, and conduct monitored staging smoke tests. Never paste credentials into GitHub or commit `.env`. No OCI resources were created or modified.

## Image architecture gate
`staging.sh --start` now invokes `verify-image-platforms.py` before any Compose startup. It reads Docker registry manifests for `pgvector/pgvector:pg16` and `redis:7` and rejects a target host whose Linux CPU architecture is not advertised. This requires registry network access and does **not** prove that locally built Identity/Trust/Registry images will build and run on the target CPU; those must still be built and smoke-tested on the actual OCI host. Manifest tags are mutable: pin reviewed digests before production promotion. CI uses mocked manifests to verify fail-closed logic; the live OCI platform check is only performed on the selected host.

## Test fixture correction
Newline and duplicate-key regression fixtures now contain real line breaks rather than literal backslash-n sequences. These tests still require CI execution before acceptance.

## Operator evidence gate
Before `staging.sh --start`, the operator must export `AEPX_BACKUP_RESTORE_VERIFIED=yes` and `AEPX_IMAGE_PLATFORMS_VERIFIED=yes` **and** point `AEPX_BACKUP_RESTORE_EVIDENCE` and `AEPX_IMAGE_PLATFORM_EVIDENCE` to two regular, non-symlink, nonempty local evidence files created within the last seven days. A small metadata guard validates existence, age and size. Keep evidence files private and outside the repository. **Important:** this is an administrative evidence-presence gate, not cryptographic proof of the test result. Independently review actual restore output, checksum, test data, OCI shape, built-image compatibility and resource quota before approval. Never deploy on an existing production host.
