#!/usr/bin/env bash
set -Eeuo pipefail
# Read-only inventory. Run in OCI Cloud Shell with configured OCI CLI.
command -v oci >/dev/null || { echo "OCI CLI unavailable"; exit 1; }
TENANCY="${OCI_TENANCY_OCID:-}"
if [[ -z "$TENANCY" ]]; then
  TENANCY="$(oci iam tenancy get --tenancy-id "$(grep -m1 '^tenancy=' "$HOME/.oci/config" 2>/dev/null | cut -d= -f2)" --query 'data.id' --raw-output 2>/dev/null || true)"
fi
[[ "$TENANCY" == ocid1.tenancy.* ]] || { echo "Set OCI_TENANCY_OCID (tenancy OCID); no changes made"; exit 2; }
echo "Read-only Compute inventory; no secrets will be printed."
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
oci iam compartment list --compartment-id "$TENANCY" --compartment-id-in-subtree true --all --output json > "$TMP"
python3 - "$TMP" "$TENANCY" <<'PY' > "${TMP}.ids"
import json,sys
d=json.load(open(sys.argv[1]))
print(sys.argv[2])
for c in d.get('data',[]):
    if c.get('lifecycle-state')=='ACTIVE': print(c['id'])
PY
while IFS= read -r compartment; do
  echo "Compartment: $compartment"
  if ! oci compute instance list --compartment-id "$compartment" --all \
      --query 'data[].{Name:"display-name",Shape:shape,State:"lifecycle-state",Id:id}' --output table; then
    echo "Unable to list this compartment (permissions/region); continuing" >&2
  fi
done < "${TMP}.ids"
rm -f "${TMP}.ids"
echo "Inventory finished. Confirm the VM shape and OS before deployment."
