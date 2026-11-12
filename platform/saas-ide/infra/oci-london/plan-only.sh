#!/usr/bin/env bash
# Requires locally configured OCI CLI authentication; never provisions resources.
set -euo pipefail
cd "$(dirname "$0")"
: "${TF_VAR_compartment_ocid:?Set compartment OCID in protected environment}"
: "${TF_VAR_object_storage_namespace:?Set namespace in protected environment}"
: "${TF_VAR_availability_domain:?Set verified London availability domain}"
: "${TF_VAR_image_ocid:?Set verified Arm64 image OCID}"
: "${TF_VAR_ssh_public_key:?Set an SSH public key (never a private key)}"
: "${AEPX_APPROVAL_FILE:?Point to a private approval JSON file}"
python3 preflight.py "$AEPX_APPROVAL_FILE"
terraform init -input=false
terraform fmt -check -recursive
terraform validate
terraform plan -input=false -lock=true -var='enable_staging_compute=true' -out=staging.tfplan
echo "Plan saved locally. No apply has run. Review with: terraform show staging.tfplan"
