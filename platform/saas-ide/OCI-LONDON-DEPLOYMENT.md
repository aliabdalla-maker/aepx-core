# OCI London Compute deployment target — Hybrid IDE

**Console:** https://cloud.oracle.com/compute/instances?region=uk-london-1  
**OCI region:** `uk-london-1` (UK South / London)  
**Status:** Target selected; **no OCI instance has been inspected, created, modified or deployed to**.

## Intended role
Host the hybrid IDE API and its reverse proxy on an approved OCI Compute instance for a controlled staging pilot. Existing AEP-X deployment infrastructure may be reused only after inspection of the instance, running workloads and network policy. This document does not assert that an instance exists or is ready.

## Required inventory before deployment
1. Sign in to the link above and select the correct **compartment**. Confirm instance display name, OCID, availability domain, shape, operating system, private IP, VCN and subnet.
2. Confirm tenancy permissions, region subscription, quota, available disk/memory and network ingress/egress rules.
3. Inspect existing AEP-X deployment and `.github/workflows/deploy-oci.yml` for compatibility; **do not overwrite existing services or proxy routes**.
4. Confirm DNS name, HTTPS certificate management, backups, secret management, monitoring and cost budget.
5. Prefer private subnet plus load balancer or tightly controlled ingress; no database or internal service ports exposed publicly.
6. Confirm a separate staging environment and explicit production approval.

## Proposed staging topology
```text
HTTPS client -> OCI load balancer / Caddy -> IDE API (private)
                                      -> future Next.js IDE (private)
IDE API -> future OIDC verification / PostgreSQL / AEP-X gateway (private)
GitHub Actions -> approved deployment workflow -> OCI runner -> staging
```

## Configuration contract (no credentials committed)
```dotenv
OCI_REGION=uk-london-1
IDE_ENV=production
# OCI_COMPARTMENT_OCID=<set in deployment secret/variable>
# OCI_INSTANCE_OCID=<set in deployment secret/variable>
# IDE_PUBLIC_HOSTNAME=<approved DNS name>
# OIDC_ISSUER=<trusted issuer>
# OIDC_AUDIENCE=<registered client audience>
```

**Deployment gate:** The current hybrid IDE API deliberately returns HTTP 503 for project access when `IDE_ENV` is not `development`. It **must not be deployed as a usable public application** until OIDC token verification, tenant membership enforcement, PostgreSQL and security tests are implemented. Do not bypass this gate with development keys or headers.

## Operational verification checklist
- [ ] OCI instance and compartment verified by authorised operator
- [ ] Existing production routes and services inventoried
- [ ] Staging DNS and TLS configured
- [ ] Private networking, NSGs and firewall reviewed
- [ ] OIDC, tenant RBAC and audit persistence completed
- [ ] Secrets injected via approved secret manager
- [ ] Health checks, logs, alerts and backup/restore tested
- [ ] Application CI and end-to-end security tests passed
- [ ] Rollback and change approval documented

## References
- [OCI Compute instances — London](https://cloud.oracle.com/compute/instances?region=uk-london-1)
- [OCI listing instances](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/list-instances-displayingconsole.htm)
- [OCI regions](https://docs.oracle.com/en-us/iaas/Content/General/Concepts/regions.htm)
- [Existing OCI deployment workflow](../../../.github/workflows/deploy-oci.yml)
