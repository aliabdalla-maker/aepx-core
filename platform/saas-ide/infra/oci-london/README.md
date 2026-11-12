# OCI London infrastructure (plan-only)
Region is pinned to `uk-london-1`. Resources are private staging VCN, private subnet, NSG with no ingress rules, and non-public versioned Object Storage bucket. **No compute instance, public endpoint, gateway or production deployment is provisioned.**

Prerequisites: authenticated OCI CLI/SDK identity, existing compartment OCID, Object Storage namespace, quota and cost review. Run `terraform init`, `terraform validate`, `terraform plan -var compartment_ocid=... -var object_storage_namespace=...` locally after approval. Do **not** apply until operator verifies account, cost, region, resource ownership and security change request. Never commit OCIDs, credentials, Terraform state or plan files.
