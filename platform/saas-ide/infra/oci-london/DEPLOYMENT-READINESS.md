# OCI London Phase 2.23 — Staging deployment readiness

**No deployment has occurred.** Private Compose topology and Dockerfiles are staged in GitHub only.

## Blockers before deployment
- OCI London tenancy, compartment, image, availability domain and quotas are not available to this workflow.
- Actual tenancy-specific cost quote, approved budget and reviewed Terraform plan are missing.
- Terraform validation must complete successfully; the workflow is not a substitute for account-specific plan.
- The private subnet currently lacks approved operator ingress, DNS, NAT/service gateway, HTTPS load balancer, certificates and OCI Vault wiring.
- `compose.staging.yml` has no public ports by design; `internal: true` prevents outbound access. OIDC discovery and external integrations require reviewed private egress.
- PostgreSQL database initialization, migrations and database user privileges must be configured before API startup.
- The example env file is intentionally incomplete. Do not use it to launch an internet-facing service.
- Build images with pinned digests and vulnerability scans, configure backup/restore and test rollback.

## Local verification
```bash
python3 -m unittest discover -s platform/saas-ide/infra/oci-london -p 'test_*.py'
docker compose --env-file platform/saas-ide/infra/oci-london/staging.env.example \
  -f platform/saas-ide/infra/oci-london/compose.staging.yml config
```
The Compose configuration command may require an actual ignored `staging.env` and secret file; do not create or commit fake production secrets.

## Publication and release
Never merge, provision, apply Terraform, upload artifacts, modify DNS, expose an API, or enable MCP forwarding without operator authorization and completed release gates.
