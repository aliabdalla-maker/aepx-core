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
