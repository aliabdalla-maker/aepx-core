# OCI production release gates

## Current deployment tracks
- Existing `deploy-oci.yml` publishes a static AEP-X GUI via an **x64 self-hosted runner**. Do not overwrite it with the new Docker deployment.
- This PR provides a **private-first Docker stack** intended for a separate ARM64 OCI Always Free VM. It is not a public website deployment.
- The OCI CLI inventory script is read-only and does not provision or modify Compute instances.

## Release checklist
- [ ] GitHub CI for the PR passes, including `oci-compose-validate`.
- [ ] Confirm OCI VM architecture and Always Free shape from the OCI console.
- [ ] Validate that all base images build and run on the target CPU architecture.
- [ ] Check adequate RAM, storage, swap policy, and model download size.
- [ ] Remove or replace remaining hardcoded application/database credentials and verify DSN propagation.
- [ ] Validate OCI NSG/security-list and host firewall; SSH-only ingress during private testing.
- [ ] Run `deploy.sh --validate-only` on a clean, non-production host.
- [ ] Confirm backup and restore rehearsal and encrypted off-host backup storage.
- [ ] Deploy with `deploy.sh --deploy` only after the preceding gates pass.
- [ ] Check `check-host.sh`, application authentication, connector policy, gateway and console health.
- [ ] If public access is required, configure an authenticated HTTPS reverse proxy, rate limits, and monitoring before opening 80/443.
- [ ] Document tested rollback and explicit production approval before merging or promoting.

## Execution on OCI Cloud Shell
```bash
bash deploy/oci/oci-inventory.sh
```
Set `OCI_TENANCY_OCID` if auto-detection fails. Supply the **instance shape and operating system**, not passwords, private keys, or full credential output.

## Production safeguards
No automatic production deployment is included in this PR. Existing static-site deployment remains separate. Never run the fresh-install volume migration against a populated production PostgreSQL volume.
