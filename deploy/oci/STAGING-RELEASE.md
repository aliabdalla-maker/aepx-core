# Isolated OCI Ubuntu staging release

This is **not** the existing production website or the full AEP-X stack. Do not run these steps on the production server. The Compose project is `aepx-oci-staging`, with its own named PostgreSQL volume and **no published host ports**.

## Required evidence before staging startup

1. Identify the intended Ubuntu Compute instance and its CPU architecture using `oci-inventory.sh` and `host-readiness.sh`.
2. Confirm it is a dedicated staging host and that Docker and disk/memory capacity are sufficient. The 3.5 GB memory gate is a floor, **not** a measured sizing guarantee.
3. Confirm every image supports the VM architecture and that application builds succeed.
4. Use unique, strong passwords in an untracked repository-root `.env` with `chmod 600 .env`. The staging script passes `--env-file .env` explicitly; never commit secrets.
5. Take an encrypted off-host backup where applicable and complete an isolated restore rehearsal. Record evidence outside the repository.
6. Verify GitHub Actions checks on the PR head commit.

## Validation (does not start containers)

```bash
bash deploy/oci/verify-release-gates.sh
bash deploy/oci/staging.sh --validate
```

## Explicitly approved staging startup

Only after independently checking the evidence above on the intended dedicated staging VM:

```bash
AEPX_STAGING_APPROVED=yes \
AEPX_BACKUP_RESTORE_VERIFIED=yes \
AEPX_IMAGE_PLATFORMS_VERIFIED=yes \
bash deploy/oci/staging.sh --start
bash deploy/oci/staging.sh --smoke
```

These approval flags record operator assertions; the script **cannot prove** backup restoration or image compatibility. Never set them without real evidence. Startup can build images, create volumes, and consume host resources. It does not change the production Nginx or DNS configuration.

## Staging PostgreSQL backup

Once the isolated staging database is running, create a restricted logical backup with `bash deploy/oci/backup-staging.sh /absolute/private/backup/directory`. The script uses `pg_dump`, gzip integrity checking and SHA-256, and does not modify the database. The output is **not encrypted automatically**: transfer it using an encrypted off-host backup mechanism and perform an independent restore rehearsal in a disposable database before asserting the backup gate. Run `bash deploy/oci/restore-staging-rehearsal.sh /absolute/private/backup/directory/<backup-file>.sql.gz` after the backup is created. This command starts a **temporary** isolated PostgreSQL container with no network access, restores the SQL dump, checks a database query, and removes the temporary container. It requires Docker image availability and sufficient temporary storage; it never restores into the staging or production database. Never store backups in Git.

## Recovery and next gates

Check `bash deploy/oci/staging.sh --status` and Docker logs for failed services. Do not use `docker compose down -v` on staging: that deletes its database. Application HTTP endpoint tests, database restore, security acceptance, TLS/reverse-proxy design and release approval remain separate gates. The existing x86 self-hosted static-site workflow must remain unchanged.


## Operational monitoring

Run `bash deploy/oci/monitor-staging.sh` on the staging VM to check container availability and Docker health states without restarting or modifying services. It exits nonzero when a container is missing, stopped or unhealthy. Use a host-side scheduler and an external notification mechanism to alert on nonzero exit codes; neither alert delivery nor production monitoring is configured by this script. For application health and PostgreSQL/Redis probes run `bash deploy/oci/staging.sh --smoke`. Avoid logging environment files or credentials.


## CI integration acceptance (required before VM staging)

The `integration` job in `.github/workflows/oci-compose-validate.yml` builds an ephemeral Docker Compose stack, waits for PostgreSQL, Redis, Identity, Trust and Registry HTTP readiness, verifies authenticated DID issuance, persists an agent, reads it back, rejects an unverified external DID, and destroys CI volumes on completion. Check the actual Actions job logs and green status; a committed workflow is **not** evidence of execution. No OCI credentials are used by this job.

## Network and credentials policy

Staging publishes no host ports. Access is through a trusted administrative session or a separate, reviewed TLS ingress with restricted access; do not expose port 8000 or PostgreSQL to the public internet. The internal DID service key is a temporary shared credential and must be replaced by scoped service identities before public exposure. JWT issuance in secure mode remains disabled. Do not treat the health endpoint as an authentication mechanism.

## Release checklist

- [ ] Confirm PR checks pass, including the ephemeral integration job
- [ ] Verify a **dedicated non-production** OCI Ubuntu host and image architecture
- [ ] Confirm host sizing, available storage, and private secret permissions
- [ ] Verify encrypted off-host backups and a disposable restore rehearsal
- [ ] Review staging ingress, TLS and firewall configuration (no public service ports by default)
- [ ] Start staging only with truthful operator approval flags
- [ ] Run `bash deploy/oci/staging.sh --smoke` and `bash deploy/oci/monitor-staging.sh`
- [ ] Configure alert delivery, secret rotation and documented rollback
- [ ] Obtain security and functional acceptance before merging or releasing

No script in this repository can independently certify OCI access, TLS, off-host encryption, or a production rollout.


## Critical DID key-custody limitation

Secure Identity now omits `private_key_hex` from DID issuance responses to prevent intermediary disclosure. The current generated private key is **not retained or delivered to an authenticated owner**; generated DIDs are therefore not usable for future proof-of-possession signing. This is a temporary staging-only registration flow, **not production-ready decentralized identity**. Before production, implement a verifiable owner-controlled public-key registration or a properly managed signing-key custody solution, including rotation, revocation and recovery. Do not claim DID ownership verification based on this endpoint.

## Write endpoint authorization

In secure staging, Registry `POST /agents` and Trust `POST /trust/{entity_id}/adjust` require the shared `X-AEPX-Service-Key` credential. The CI integration job checks both allowed and rejected writes. This is an interim control: replace it with service-specific credentials and per-operation authorization before exposing the services beyond the isolated staging network.


## CI persistence and sensitive logging

The ephemeral integration workflow now restarts Registry and verifies that its test agent remains readable from PostgreSQL. A passing test proves only that CI's disposable environment persisted this record across an application restart; it does not establish recovery from host loss or an OCI backup. CI failure diagnostics intentionally omit application logs because DID responses and service credentials may be sensitive. Collect and redact logs only through an approved restricted incident process.


## Monitoring tuning

`deploy/oci/monitor-staging.sh` requires every container to report Docker health `healthy`; missing or unconfigured health checks fail closed. Optionally set `AEPX_ALERT_WEBHOOK_URL` to a trusted HTTPS endpoint in the monitor's runtime environment. The script sends a generic JSON `text` notification only on failure and never transmits credentials. Confirm the receiver accepts this payload format and test delivery before relying on it. Cron/systemd scheduling, delivery retries, deduplication, paging and escalation remain operator tasks. The webhook URL itself may be sensitive; store it in a restricted environment file, never in Git.

Registry startup now requires Identity's healthy state. This improves initial ordering but does not guarantee continued downstream availability after startup; use the smoke test and monitor for ongoing checks.


## Encrypted backups (new)

Install the `age` CLI on the staging host. Generate an age recipient/identity pair on a trusted administrator system, and protect the private identity separately from the staging VM. Set `AEPX_BACKUP_AGE_RECIPIENT` to the public `age1...` recipient and run:

```bash
AEPX_BACKUP_AGE_RECIPIENT='age1...' bash deploy/oci/backup-staging-encrypted.sh /absolute/private/backup-directory
```

The encrypted `.sql.gz.age` and checksum must be transferred off-host to access-controlled storage using an operator-approved mechanism. For recovery rehearsal, supply a private key file via `AEPX_BACKUP_AGE_IDENTITY=/secure/path/identity.txt` and run `bash deploy/oci/restore-staging-encrypted-rehearsal.sh /absolute/backup.sql.gz.age`. The script decrypts into a private temporary directory, validates gzip, and restores to a disposable PostgreSQL container, not staging or production. Do not store the private identity in Git or alongside backups. The temporary decrypted file may be written to disk during the rehearsal: use an encrypted filesystem and secure host. These scripts have been committed but have not yet been executed on OCI.


## Encrypted recovery CI acceptance

The OCI validation workflow includes a disposable `age` encryption/decryption and PostgreSQL restore fixture and verifies that a modified ciphertext is rejected by SHA-256 validation. The recovery identity must be an ordinary private file with no group/world permissions; the encrypted backup path must be absolute. A successful fixture does **not** establish that a real OCI backup is complete, that off-host copies are accessible, or that the application can recover within the required RTO/RPO. Run a separately approved real-data restore rehearsal before any release.


## Backup script hardening (current branch)

Encrypted backup filenames include a random suffix to avoid same-second collisions. The script validates the public age recipient format and stages both ciphertext and checksum before publication. Recovery requires absolute backup and private identity paths and rejects directly symlinked backup parents. These are defense-in-depth checks, not a substitute for protected filesystem mounts, off-host immutable storage, or verified restore evidence. Run `bash -n deploy/oci/backup-staging-encrypted.sh deploy/oci/restore-staging-encrypted-rehearsal.sh` and the CI encrypted recovery job before approving a deployment.


## Trust API safety

The Trust read endpoint no longer inserts rows for unknown entity IDs. It returns a default score of 50 without persistence; only authenticated adjustment writes create/update records in secure staging. Unknown adjustment components return HTTP 422. The OCI validation workflow now triggers on `schemas/sql/**` changes and includes integration checks for default trust reads and invalid adjustments. Verify the full workflow before approving staging deployment.


## Scoped service credential migration

The isolated Compose overlay supports three optional independent secrets: `AEPX_REGISTRY_IDENTITY_KEY` (Registry → Identity DID minting), `AEPX_REGISTRY_WRITE_KEY` (Registry agent creation), and `AEPX_TRUST_WRITE_KEY` (Trust score mutation). Configure all three with different 32+ character random URL-safe values in private `.env`, then update authorised clients to use the matching credential per endpoint. The validator checks uniqueness. If a dedicated key is unset, the relevant service falls back to `AEPX_INTERNAL_SERVICE_KEY` for backward compatibility; **do not treat this as completed least-privilege isolation**. The shared key remains injected into the containers and must be retired in a separate coordinated migration with contract tests. Never expose write keys in public browser clients. The DID signing-key custody / proof-of-possession issue remains a release blocker.


## Scoped authorization regression tests

CI now includes negative tests proving that a configured dedicated Registry→Identity credential, Registry write credential, and Trust write credential each supersede the legacy shared credential at the corresponding endpoint. The secret validator rejects symlinked `.env` files. These tests are committed but must pass in GitHub Actions before the migration can be accepted. Coordinate credential rotation and client configuration before disabling the fallback. Never apply staging secrets or deployment commands to production.


## Current acceptance evidence and remaining blockers

The ephemeral integration workflow now asserts that a GET for an unknown Trust entity leaves no row in PostgreSQL. The isolated logical restore rejects non-absolute or symlinked backup paths and checksum manifests. Neither change constitutes a successful CI run: inspect the Actions job results and logs before approving the release.

**Next engineering gates (in order):** (1) run and repair CI to green; (2) provision and rotate three scoped secrets, update authorised callers and remove shared-key fallback; (3) implement DID proof-of-possession and persistent, protected signing-key custody (prefer managed KMS/HSM, never return raw private keys in secure mode); (4) verify actual OCI instance shape/architecture and image compatibility; (5) deploy only to approved isolated staging, configure private TLS access and monitoring; (6) test encrypted off-host recovery, application-level restore and rollback with measured RTO/RPO. Production is out of scope until separately approved.
