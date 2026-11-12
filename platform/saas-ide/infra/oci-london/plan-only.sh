#!/usr/bin/env bash
# Read-only Terraform plan for OCI London; never applies infrastructure.
set -euo pipefail
cd "$(dirname "$0")"
: "${TF_VAR_compartment_ocid:?Set verified compartment OCID locally}"
: "${TF_VAR_object_storage_namespace:?Set verified Object Storage namespace locally}"
: "${TF_VAR_availability_domain:?Set verified London availability domain}"
: "${TF_VAR_image_ocid:?Set verified Arm64 image OCID}"
: "${TF_VAR_ssh_public_key:?Set a public SSH key only}"
if [[ "${TF_VAR_instance_shape:-VM.Standard.A1.Flex}" != "VM.Standard.A1.Flex" ]]; then
  echo "Refusing non-Always-Free Compute shape" >&2
  exit 1
fi
terraform init -input=false
terraform fmt -check -recursive
terraform validate
# Terraform plan is non-provisioning; reviewed plan and separate approvals are required before apply.
terraform plan -input=false -lock=true -var='enable_staging_compute=true' -out=staging.tfplan
echo "Plan saved locally. NO apply performed. Review: terraform show staging.tfplan"
