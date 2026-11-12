#!/usr/bin/env bash
# Read-only inventory: no OCI resources created or modified.
set -euo pipefail
: "${OCI_COMPARTMENT_OCID:?Set OCI_COMPARTMENT_OCID locally; do not commit it}"
command -v oci >/dev/null || { echo "OCI CLI required" >&2; exit 1; }
echo "OCI tenancy home region (read-only):"
oci iam region-subscription list --output json
echo "Existing instances in selected London compartment:"
oci compute instance list --region uk-london-1 --compartment-id "$OCI_COMPARTMENT_OCID" --output json
echo "Available Compute shapes in London compartment:"
oci compute shape list --region uk-london-1 --compartment-id "$OCI_COMPARTMENT_OCID" --output json
echo "Availability domains:"
oci iam availability-domain list --region uk-london-1 --compartment-id "$OCI_COMPARTMENT_OCID" --output json
echo "Object Storage namespace:"
oci os ns get --region uk-london-1 --output json
echo "Review quota and remaining Always Free usage in the OCI Console. No mutations performed."
