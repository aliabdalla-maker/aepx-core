#!/usr/bin/env bash
# Read-only Terraform plan for OCI London; never applies infrastructure.
set -euo pipefail
cd "$(dirname "$0")"
# Operator-selected compartment is an identifier, not a credential.
export TF_VAR_compartment_ocid="${TF_VAR_compartment_ocid:-ocid1.compartment.oc1..aaaaaaaaonhka4z7ankj76ibtpr7w6saylbyqaiuadtul4to2qyvxkcwarua}"
: "${TF_VAR_object_storage_namespace:?Set verified Object Storage namespace locally}"
: "${TF_VAR_availability_domain:?Set verified London availability domain}"
: "${TF_VAR_image_ocid:?Set verified Arm64 image OCID}"
: "${TF_VAR_ssh_public_key:?Set a public SSH key only}"
if [[ "${TF_VAR_instance_shape:-VM.Standard.A1.Flex}" != "VM.Standard.A1.Flex" ]]; then
  echo "Refusing non-Always-Free Compute shape" >&2
  exit 1
fi
if [[ ! "${TF_VAR_compartment_ocid}" =~ ^ocid1[.]compartment[.] ]]; then
  echo "Invalid compartment OCID" >&2
  exit 1
fi
if [[ ! "${TF_VAR_image_ocid}" =~ ^ocid1[.]image[.] ]]; then
  echo "Invalid image OCID" >&2
  exit 1
fi
if [[ ! "${TF_VAR_ssh_public_key}" =~ ^(ssh-ed25519|ssh-rsa|ecdsa-sha2-) ]]; then
  echo "Only SSH public keys accepted" >&2
  exit 1
fi
if [[ "${TF_VAR_instance_ocpus:-1}" != "1" || "${TF_VAR_instance_memory_gb:-6}" != "6" ]]; then
  echo "Phase 2.26 requires the conservative 1 OCPU / 6 GB configuration" >&2
  exit 1
fi
if [[ "${TF_VAR_enable_staging_compute:-false}" == "true" ]]; then
  echo "Do not enable staging through environment; planning only" >&2
  exit 1
fi
terraform init -input=false
terraform fmt -check -recursive
terraform validate
# Terraform plan is non-provisioning; reviewed plan and separate approvals are required before apply.
terraform plan -input=false -lock=true -var='enable_staging_compute=true' -out=staging.tfplan
terraform show -json staging.tfplan > staging.plan.json
python3 verify-plan.py staging.plan.json
echo "Plan saved locally. NO apply performed. Review: terraform show staging.tfplan"
