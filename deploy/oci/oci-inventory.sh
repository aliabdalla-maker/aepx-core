#!/usr/bin/env bash
set -Eeuo pipefail
command -v oci >/dev/null || { echo "OCI CLI required (run from OCI Cloud Shell)"; exit 1; }
echo "Region: $(oci iam region-subscription list --query 'data[]."region-name"' --raw-output 2>/dev/null || true)"
echo "Discovering accessible compartments and Compute instances (read-only)..."
TENANCY="${OCI_TENANCY_OCID:-}"
if [[ -z "$TENANCY" ]]; then
  TENANCY="$(oci iam compartment list --compartment-id-in-subtree true --all --query 'data[0]."compartment-id"' --raw-output)"
fi
[[ "$TENANCY" == ocid1.tenancy.* ]] || { echo "Set OCI_TENANCY_OCID to your tenancy OCID"; exit 2; }
echo "Tenancy scope verified"
oci iam compartment list --compartment-id "$TENANCY" --compartment-id-in-subtree true --all --query 'data[].{Name:name,OCID:id,State:"lifecycle-state"}' --output table
echo "List instances in your selected compartment using:"
echo 'oci compute instance list --compartment-id "$COMPARTMENT_OCID" --all --query '\''data[].{Name:"display-name",Shape:shape,State:"lifecycle-state",Id:id}'\'' --output table'
echo "This script makes no OCI changes."
