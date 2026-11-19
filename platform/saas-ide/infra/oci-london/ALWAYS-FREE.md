# OCI Always Free staging — uk-london-1

Current Oracle Always Free tenancy allowances (verify in your own Console):
- Ampere A1 Flex: 1,500 OCPU-hours and 9,000 GB-hours per month, equivalent to **2 OCPUs and 12 GB** continuously for Always Free tenancies.
- A1 uses **Arm64**, not x86_64. Select an Always Free-eligible Arm64 Oracle Linux or Ubuntu image. Confirm application dependencies and container image architecture.
- Always Free eligibility applies **only in the tenancy home region**. If home region is not uk-london-1, this deployment is blocked.
- The allowance is shared with existing A1 instances. Proposed VM defaults to **1 OCPU / 6 GB**, subject to verified remaining allowance.
- Previous E4 Flex configuration was not Always Free eligible and has been removed from the Compute resource.
- Boot volumes, Object Storage, backups, bandwidth and other resources have their own limits. Do not assume unlimited free storage or zero charges.
- The private subnet has no outbound route or bastion. No instance can be operated until secure access and patching are designed and approved.
- A1 capacity may be unavailable. Do not silently substitute a paid shape or change region.
- The private draft-artifacts bucket is versioned; delete old versions to avoid storage growth beyond free allocation.
- No automatic apply, paid upgrade, OCI account changes, DNS publication, or external MCP dispatch.

## Console verification
1. Visit https://cloud.oracle.com/?region=uk-london-1 and check **Tenancy details → Home region**.
2. Inspect **Compute → Instances** for existing A1 usage and **Governance → Limits, Quotas and Usage**.
3. Check **Compute → Create instance** for **Always Free eligible** A1 Flex shape and an Arm64 OS image; record the verified AD and image OCID.
4. Review **Cost Analysis/Budgets** and approve any projected non-free resource charges.
5. Run read-only inventory, offline preflight, `terraform validate`, and `terraform plan`. Do not run `terraform apply` until approved.

References: https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
