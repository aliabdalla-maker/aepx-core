#!/usr/bin/env bash
# Read-only OCI London discovery. No OCI create/update/delete calls.
set -euo pipefail
command -v oci >/dev/null || { echo "Install/configure OCI CLI first" >&2; exit 1; }
echo "Tenancy region subscriptions:"
oci iam region-subscription list --output table
echo "Compartments visible to current identity (select a compartment OCID locally):"
: "${OCI_TENANCY_OCID:?Set tenancy OCID locally (never commit credentials)}"
oci iam compartment list --compartment-id "$OCI_TENANCY_OCID" --compartment-id-in-subtree true --access-level ACCESSIBLE --lifecycle-state ACTIVE --output table
echo "London Object Storage namespace:"
oci os ns get --region uk-london-1 --output table
echo "This script does not create a compartment or any other OCI resource."
