"""Read-only inspection of Terraform JSON plan. Never invokes terraform apply."""
import json
import sys
from pathlib import Path

ALLOWED = {
    "oci_core_vcn", "oci_core_subnet", "oci_core_network_security_group",
    "oci_objectstorage_bucket", "oci_core_instance",
}

def inspect(plan):
    problems = []
    changes = plan.get("resource_changes", [])
    if not changes:
        problems.append("No planned resource changes; check configuration")
    instances = 0
    for resource in changes:
        kind = resource.get("type")
        actions = resource.get("change", {}).get("actions", [])
        after = resource.get("change", {}).get("after") or {}
        if kind not in ALLOWED:
            problems.append(f"Unexpected resource type: {kind}")
        if any(action not in ("create", "no-op", "read") for action in actions):
            problems.append(f"Existing resource mutation prohibited: {resource.get('address')}")
        if kind == "oci_core_instance" and "create" in actions:
            instances += 1
            if after.get("shape") != "VM.Standard.A1.Flex":
                problems.append("Non-A1 Compute shape")
            if not isinstance(after.get("create_vnic_details"), list) or len(after["create_vnic_details"]) != 1 or after["create_vnic_details"][0].get("assign_public_ip") is not False:
                problems.append("Public IP must be disabled")
            shape_config = after.get("shape_config")
            if not isinstance(shape_config, list) or len(shape_config) != 1:
                problems.append("Explicit A1 sizing required")
            else:
                cpu = shape_config[0].get("ocpus")
                ram = shape_config[0].get("memory_in_gbs")
                if type(cpu) not in (int, float) or not 1 <= cpu <= 2:
                    problems.append("Invalid OCPU project cap")
                if type(ram) not in (int, float) or not 4 <= ram <= 12 or (type(cpu) in (int, float) and ram > cpu * 6):
                    problems.append("Invalid memory project cap")
            source = after.get("source_details")
            if not isinstance(source, list) or len(source) != 1 or source[0].get("boot_volume_size_in_gbs") != 50:
                problems.append("Boot volume must be 50 GB")
        if kind == "oci_objectstorage_bucket" and after.get("access_type") != "NoPublicAccess":
            problems.append("Bucket must remain private")
    if instances != 1:
        problems.append(f"Expected one staging instance, found {instances}")
    return problems

def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python3 verify-plan.py terraform-plan.json")
    problems = inspect(json.loads(Path(sys.argv[1]).read_text()))
    for problem in problems:
        print("BLOCKED:", problem)
    if problems:
        raise SystemExit(1)
    print("Plan structure passed offline safety checks. Account costs and approval remain separate gates.")

if __name__ == "__main__":
    main()
