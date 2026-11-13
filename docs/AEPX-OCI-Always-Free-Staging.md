# AEP-X on OCI Always Free: constrained private staging

This repository provides a **minimal, private, staging-only** Docker Compose profile under `deploy/oci-always-free`. It does **not** provision an OCI VM, VCN, domain, certificate, production database or public ingress. No OCI charges or Always Free eligibility can be guaranteed by GitHub configuration.

## Before deploying
1. In OCI UK South (London), verify the tenancy's **actual Always Free eligible shape, available OCPU/memory, storage, region and quotas**. Existing VCN quota errors must be resolved by using an authorised existing network or approved quota changes; do not delete production VCNs.
2. Use an Ubuntu Always Free eligible VM only if capacity is available. Limit block volume allocations to your tenancy's free allowance and verify the cost estimate in OCI Console. Never enable paid resources or upgrade without explicit approval.
3. Keep ingress private. Only loopback port 8000 is published by this Compose profile. Access via SSH port forwarding or a separately configured authenticated TLS proxy. Do not open 8000 or PostgreSQL to the internet.
4. Provision Docker Engine/Compose using supported Ubuntu instructions. Use a root-owned, permission-restricted environment file outside Git with a strong random database password. Protect Docker socket access.
5. Review service environment, initialization, image provenance, storage, and memory before starting. This is a **subset** of the platform, not CrewAI/MCP/HITL production deployment.

## Read-only validation
```bash
export AEPX_POSTGRES_PASSWORD='<supply securely; never commit>'
bash deploy/oci-always-free/preflight.sh
docker compose -f deploy/oci-always-free/compose.yml config --quiet
```
After manual review, a staging operator may run:
```bash
docker compose -f deploy/oci-always-free/compose.yml up -d --build
docker compose -f deploy/oci-always-free/compose.yml ps
```
**Do not run this on an existing production host without isolation and rollback approval.**

## Known limitations and next work
- Some current services rely on preexisting SQL initialization and in-memory state; this profile is not validated for full functionality.
- Gateway routes reference additional services that are not in the minimal profile.
- No authenticated external ingress, OCI Vault wiring, immutable image digest pinning, encrypted backup automation or disaster-recovery drill.
- No PostgreSQL HITL API or real MCP/CrewAI/RAG end-to-end integration.
- OCI Compute shape and actual free resource availability are unverified.
- Full deployment requires CI checks, dependency health probes, security review, secrets handling, backup/restore evidence and release approval.
