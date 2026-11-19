"""Offline, fail-closed OCI London deployment preflight. No OCI API calls."""
import argparse
import json
import re
from pathlib import Path

OCID = re.compile(r"^ocid1\.(?:compartment|tenancy|image)\.[a-z0-9._-]+$")
def check(data):
    errors = []
    if data.get("tenancy_home_region") != "uk-london-1":
        errors.append("Always Free resources require tenancy home region uk-london-1")
    if data.get("instance_shape") != "VM.Standard.A1.Flex":
        errors.append("Only Always Free VM.Standard.A1.Flex permitted")
    usage_keys = ("existing_a1_ocpus", "existing_a1_memory_gb", "instance_ocpus", "instance_memory_gb")
    if any(not isinstance(data.get(k), (int, float)) or data[k] < 0 for k in usage_keys):
        errors.append("Existing A1 tenancy usage and proposed sizing must be verified")
    elif data["existing_a1_ocpus"] + data["instance_ocpus"] > 2 or data["existing_a1_memory_gb"] + data["instance_memory_gb"] > 12:
        errors.append("A1 usage would exceed Always Free tenancy allowance")
    if data.get("region") != "uk-london-1":
        errors.append("Region must be uk-london-1")
    for key, prefix in (("compartment_ocid", "ocid1.compartment."), ("image_ocid", "ocid1.image.")):
        if not str(data.get(key, "")).startswith(prefix) or not OCID.fullmatch(str(data.get(key, ""))):
            errors.append(f"Invalid {key}")
    if not str(data.get("availability_domain", "")).strip():
        errors.append("Availability domain must be verified")
    if not data.get("operator_approved", False):
        errors.append("Explicit operator approval required")
    if not data.get("security_review_approved", False):
        errors.append("Security review required")
    if not data.get("cost_review_approved", False):
        errors.append("Cost review required")
    if not isinstance(data.get("estimated_monthly_gbp"), (int, float)) or data.get("estimated_monthly_gbp", -1) < 0:
        errors.append("Validated nonnegative monthly cost estimate required")
    if not isinstance(data.get("budget_cap_gbp"), (int, float)) or data.get("budget_cap_gbp", 0) <= 0:
        errors.append("Positive approved monthly budget required")
    elif isinstance(data.get("estimated_monthly_gbp"), (int, float)) and data["estimated_monthly_gbp"] > data["budget_cap_gbp"]:
        errors.append("Estimated cost exceeds approved budget")
    if data.get("public_ip_enabled", True):
        errors.append("Public IP prohibited for staging")
    if data.get("automatic_mcp_dispatch_enabled", True):
        errors.append("Automatic MCP dispatch prohibited")
    if not data.get("terraform_plan_reviewed", False):
        errors.append("Terraform plan review required")
    return errors

def main():
    p = argparse.ArgumentParser()
    p.add_argument("approval_json", type=Path)
    args = p.parse_args()
    issues = check(json.loads(args.approval_json.read_text()))
    if issues:
        for issue in issues:
            print("BLOCKED:", issue)
        raise SystemExit(1)
    print("Preflight checks passed; this does NOT authorize or perform terraform apply.")

if __name__ == "__main__":
    main()
