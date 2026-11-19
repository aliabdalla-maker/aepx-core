#!/usr/bin/env bash
set -euo pipefail
: "${OCI_COMPARTMENT_OCID:?Set OCI_COMPARTMENT_OCID locally; do not commit it}"
command -v oci >/dev/null || { echo "OCI CLI required" >&2; exit 1; }
echo "Read-only OCI London inventory. Confirm CLI profile and permissions before continuing."
oci iam region-subscription list --output json
oci compute instance list --region uk-london-1 --compartment-id "$OCI_COMPARTMENT_OCID" --query 'data[].{name:"display-name",shape:shape,state:"lifecycle-state"}' --output json
oci limits resource-availability get --region uk-london-1 --compartment-id "$OCI_COMPARTMENT_OCID" --service-name compute --limit-name standard-e4-core-count --output json
echo "Inventory only. No resources created or changed."
