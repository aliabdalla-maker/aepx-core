# Phase 2.22 — OCI London dedicated staging approval gate

**Region:** uk-london-1. **Default:** enable_staging_compute=false.
**State:** design only, no Terraform apply or account access.

## Before provisioning
1. Confirm tenancy, compartment OCID, Object Storage namespace, availability domain and a compatible image OCID directly in the OCI console.
2. Obtain live pricing and estimated monthly costs for A1 Flex OCPUs, RAM, boot volume, Object Storage versioning, backups, egress, load balancer, logging and taxes. Region and account discounts affect totals. No monthly price is asserted here.
3. Set a monthly OCI budget with alert thresholds and approve a maximum spend. A budget alert is not an automatic hard spending cap.
4. Confirm London is the tenancy HOME region, A1 Arm64 capacity and remaining Always Free allocation; verify quotas, IAM policies, network routing and availability of a controlled operator access path (OCI Bastion or equivalent).
5. Inspect Terraform plan, particularly any unexpected deletes, public IPs, ingress, network routes or changes to existing resources.
6. Confirm the private subnet currently has no NAT or service gateway; the VM will have no outbound package/update access until an explicitly reviewed private egress path is added.
7. Obtain explicit approval for the exact plan and estimated cost before `terraform apply`.

## Example plan-only commands
```bash
cd platform/saas-ide/infra/oci-london
terraform init
terraform fmt -recursive
terraform validate
terraform plan \
  -var="compartment_ocid=YOUR_VERIFIED_COMPARTMENT_OCID" \
  -var="object_storage_namespace=YOUR_VERIFIED_NAMESPACE" \
  -var="availability_domain=YOUR_VERIFIED_AD" \
  -var="image_ocid=YOUR_VERIFIED_LONDON_IMAGE_OCID" \
  -var="ssh_public_key=YOUR_PUBLIC_KEY" \
  -var="enable_staging_compute=true" \
  -out=staging.tfplan
terraform show staging.tfplan
```

Do not place secrets or identifying OCI tenancy values in GitHub issues or chat. Use protected Terraform variables and remote encrypted state with locking in an approved workflow. This plan does not configure an application deployment, TLS or OIDC. The application remains unavailable until those gates pass.
