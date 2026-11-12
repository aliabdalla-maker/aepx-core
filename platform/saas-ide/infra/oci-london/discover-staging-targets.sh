#!/usr/bin/env bash
# OCI London staging target discovery: read-only CLI calls, no provisioning.
set -euo pipefail
REGION=uk-london-1
COMPARTMENT="ocid1.compartment.oc1..aaaaaaaaonhka4z7ankj76ibtpr7w6saylbyqaiuadtul4to2qyvxkcwarua"
command -v oci >/dev/null || { echo "OCI CLI missing; configure OCI CLI locally." >&2; exit 1; }
echo "=== Selected compartment (read-only) ==="
oci iam compartment get --compartment-id "$COMPARTMENT" --output json
echo "=== Availability domains ==="
oci iam availability-domain list --region "$REGION" --compartment-id "$COMPARTMENT" --output json
echo "=== A1 Flex shape offerings ==="
oci compute shape list --region "$REGION" --compartment-id "$COMPARTMENT" --all --output json
echo "=== Available platform images (verify Arm64 architecture manually) ==="
oci compute image list --region "$REGION" --compartment-id "$COMPARTMENT" --lifecycle-state AVAILABLE --all --output json
echo "=== Existing compute instances ==="
oci compute instance list --region "$REGION" --compartment-id "$COMPARTMENT" --all --output json
echo "=== Existing boot volumes by AD (review in Console for tenancy-wide usage) ==="
oci bv boot-volume-attachment list --region "$REGION" --compartment-id "$COMPARTMENT" --output json
echo "=== Object Storage namespace ==="
oci os ns get --region "$REGION" --output json
echo "STOP: review A1 usage across all compartments, image Arm64 compatibility, quotas and pricing. No changes made."
