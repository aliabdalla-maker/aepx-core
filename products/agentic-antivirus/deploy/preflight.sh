#!/usr/bin/env bash
# OCI Always Free preflight for Agentic Antivirus (OCI-01..07). READ-ONLY: lists and checks only; creates,
# changes and deletes nothing. Stops at the first condition that could incur charges or that cannot be verified.
# Run in OCI Cloud Shell or with an authenticated OCI CLI:  AAV_COMPARTMENT_OCID=ocid1.compartment... ./preflight.sh
set -euo pipefail
REGION="uk-london-1"
fail() { echo "STOP: $*" >&2; exit 1; }
command -v oci >/dev/null || fail "OCI CLI not available"
[ -n "${AAV_COMPARTMENT_OCID:-}" ] || fail "AAV_COMPARTMENT_OCID not set (register PRJ-31)"
TENANCY=$(oci iam compartment get --compartment-id "$AAV_COMPARTMENT_OCID" --query 'data."compartment-id"' --raw-output 2>/dev/null) \
  || fail "cannot read the compartment: authenticate and check the OCID"
[ "$(oci iam region-subscription list --query "data[?\"region-name\"=='$REGION'] | length(@)" --raw-output)" = "1" ] \
  || fail "tenancy is not subscribed to $REGION"
echo "1/7 region $REGION and compartment verified"

AD=$(oci iam availability-domain list --region "$REGION" --compartment-id "$TENANCY" --query 'data[0].name' --raw-output)
oci compute shape list --region "$REGION" --compartment-id "$AAV_COMPARTMENT_OCID" --availability-domain "$AD" \
  --query "data[?shape=='VM.Standard.A1.Flex'].shape | [0]" --raw-output | grep -q VM.Standard.A1.Flex \
  || fail "VM.Standard.A1.Flex not offered in $AD"
echo "2/7 shape VM.Standard.A1.Flex available in $AD"

avail() { oci limits resource-availability get --region "$REGION" --compartment-id "$TENANCY" --service-name "$1" \
  --limit-name "$2" ${3:+--availability-domain "$3"} --query 'data.available' --raw-output; }
CORES=$(avail compute standard-a1-core-count "$AD"); MEM=$(avail compute standard-a1-memory-count "$AD")
echo "   free A1 cores: $CORES, free A1 memory (GB): $MEM"
awk "BEGIN{exit !($CORES >= 2 && $MEM >= 12)}" || fail "not enough Always Free A1 capacity (need 2 OCPU / 12 GB)"
echo "3/7 Always Free A1 quota sufficient"

IMG=$(oci compute image list --region "$REGION" --compartment-id "$AAV_COMPARTMENT_OCID" --operating-system "Canonical Ubuntu" \
  --shape VM.Standard.A1.Flex --sort-by TIMECREATED --query 'data[0]."display-name"' --raw-output)
[ -n "$IMG" ] && [ "$IMG" != "null" ] || fail "no Ubuntu image compatible with A1.Flex"
echo "4/7 image: $IMG"

BV=$(oci bv volume list --region "$REGION" --compartment-id "$AAV_COMPARTMENT_OCID" --query 'sum(data[?"lifecycle-state"==`AVAILABLE`]."size-in-gbs")' --raw-output 2>/dev/null || echo 0)
BOOT=$(oci bv boot-volume list --region "$REGION" --compartment-id "$AAV_COMPARTMENT_OCID" --availability-domain "$AD" --query 'sum(data[]."size-in-gbs")' --raw-output 2>/dev/null || echo 0)
TOTAL=$(( ${BV%.*} + ${BOOT%.*} ))
[ "$TOTAL" -le 150 ] || fail "block + boot volumes already use ${TOTAL} GB; Always Free allows 200 GB total and this plan needs 50 GB"
echo "5/7 storage in use: ${TOTAL} GB (plan adds at most 50 GB boot volume)"

LBS=$(oci lb load-balancer list --region "$REGION" --compartment-id "$AAV_COMPARTMENT_OCID" --query 'length(data)' --raw-output 2>/dev/null || echo 0)
echo "6/7 existing load balancers: $LBS (this plan creates none; ingress uses the VM's existing reverse proxy)"

oci compute instance list --region "$REGION" --compartment-id "$AAV_COMPARTMENT_OCID" \
  --query 'data[?"lifecycle-state"==`RUNNING`].{name:"display-name",shape:shape,ocpus:"shape-config".ocpus,memory:"shape-config"."memory-in-gbs"}' --output table
NONFREE=$(oci compute instance list --region "$REGION" --compartment-id "$AAV_COMPARTMENT_OCID" \
  --query 'length(data[?"lifecycle-state"==`RUNNING` && shape!=`VM.Standard.A1.Flex` && shape!=`VM.Standard.E2.1.Micro`])' --raw-output)
[ "$NONFREE" = "0" ] || fail "compartment runs $NONFREE non-Always-Free instance(s); review costs before continuing"
echo "7/7 no paid compute in the compartment"
python3 "$(dirname "$0")/guard.py" >/dev/null || fail "compose guard failed"
echo "PREFLIGHT PASSED. Nothing was created. Deployment still needs written approval (register RA-10)."
