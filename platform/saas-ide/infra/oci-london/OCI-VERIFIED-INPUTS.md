# AEP-X staging — operator-confirmed OCI facts (2026-11-12)

Operator confirmed:
- OCI tenancy home region: **uk-london-1**
- **VM.Standard.A1.Flex** is shown as available / Always Free eligible in their OCI Console.
- Requested action: prepare staging **without provisioning chargeable resources**.

Still unverified by automation (must not assume):
- tenancy and compartment OCIDs, namespace, availability domain, image OCID, existing A1 OCPU/GB consumption and remaining quotas;
- A1 actual launch capacity, free boot-volume/storage usage, pricing/budget, IAM privileges, and approved SSH public key;
- Terraform provider validation and account-specific plan; no apply has run.

Do not commit real OCIDs, SSH keys, secrets, or cost documents. Keep `enable_staging_compute=false` until plan approval. The account facts above do not authorize provisioning.
