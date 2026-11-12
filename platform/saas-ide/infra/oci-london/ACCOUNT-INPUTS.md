# Phase 2.26 — OCI London account discovery (read-only)

Operator-selected compartment: `ocid1.compartment.oc1..aaaaaaaaonhka4z7ankj76ibtpr7w6saylbyqaiuadtul4to2qyvxkcwarua` (from OCI Console link). The compartment OCID is configured as the Terraform default; its IAM access and existence have **not** been independently checked.

Confirmed by operator: home region `uk-london-1`; `VM.Standard.A1.Flex` appears Always Free eligible. These confirmations do **not** prove launch capacity, remaining tenancy quota, storage availability, or zero charges.

## Operator steps
1. Sign in at https://cloud.oracle.com/?region=uk-london-1.
2. Open **Identity & Security → Compartments**. Open the selected compartment and verify its displayed name, active lifecycle state, and IAM permissions. Do not create another compartment.
3. Configure OCI CLI securely on your own workstation or an approved CI runner; never paste API private keys, passwords, session tokens or auth codes into GitHub issues or chat.
4. Set `OCI_TENANCY_OCID` locally and run `bash discover-account.sh` for visible compartments and namespace.
5. The inventory script defaults to the selected compartment. Run `bash oci-inventory.sh` to inspect region, instances, shapes, availability domains and namespace.
6. In the console, verify **actual remaining** A1 OCPU/memory, image architecture (Arm64), existing boot/block volume allocations, Object Storage consumption, IAM permissions, and cost exposure.
7. Only after verification, set `TF_VAR_object_storage_namespace`, `TF_VAR_availability_domain`, `TF_VAR_image_ocid` and `TF_VAR_ssh_public_key` locally. Do not supply private keys.
8. Run `bash plan-only.sh` from this directory. This runs Terraform init/validate/plan and a read-only JSON plan checker. It **does not** apply changes.
9. Review `terraform show staging.tfplan` and validate actual cost and security impact before seeking separate provisioning approval.

## Strict HOLD conditions
- Unverified compartment permissions, remaining Always Free usage, Arm64 image, AD or account permissions.
- No reviewed plan, security approval or cost approval.
- Terraform state, local plan and OCI CLI credentials must remain outside Git.
- Do not run `terraform apply`, create chargeable resources, open public ports or enable MCP external dispatch.

A successful plan is not a guarantee that OCI will provide A1 capacity at launch time or that all accompanying services are free.
