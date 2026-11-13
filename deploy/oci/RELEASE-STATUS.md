# AEP-X OCI deployment release status

## Implemented in PR #35
- Read-only OCI compartment/Compute inventory.
- Read-only Ubuntu host architecture/capacity inspection.
- Docker CE installation script for a dedicated Ubuntu host (manual execution only).
- Private Compose overlay generation with one YAML entry per service.
- Loopback-only published ports and static security preflight.
- PostgreSQL backup script and isolated restore rehearsal instructions.
- CI validation for shell syntax, Compose resolution, port binding, and duplicate keys.
- Production blocker audit and release gates.

## Deliberately not executed
- No OCI VM provisioned or modified.
- No existing Nginx site, runner, DNS or TLS settings modified.
- No production containers started; `deploy.sh --deploy` is intentionally blocked.
- No database credentials changed or migrations applied.
- No GitHub PR merged.

## Blockers requiring actual runtime evidence
1. OCI instance shape, architecture, OS, free RAM and disk.
2. Docker image ARM64/x64 compatibility and real resource footprint.
3. Remove all development credentials, update every service DSN, and test authentication.
4. CI must pass on the PR head commit.
5. Encrypted off-host backups and an isolated successful restore rehearsal.
6. Private stack smoke tests, health probes, authorization tests and rollback.
7. HTTPS/reverse proxy configuration only after isolated acceptance.

## Commands (read-only)
```bash
bash deploy/oci/oci-inventory.sh     # OCI Cloud Shell
bash deploy/oci/host-readiness.sh    # Ubuntu VM
python3 deploy/oci/audit-compose.py # Repository checkout; reports blockers
```

## Validation command on dedicated Ubuntu host with Docker
```bash
chmod 600 .env
bash deploy/oci/deploy.sh --validate-only
```

**Do not run the fresh-install scripts on the existing production host until its workload and backup inventory are understood.**
