#!/usr/bin/env python3
"""Fail-closed static checks for the private OCI Compose overlay."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OVERLAY = ROOT / "deploy/oci/compose.secure.generated.yml"
if not OVERLAY.exists():
    sys.exit("Run deploy.sh --validate-only to generate the overlay first")
command = ["docker", "compose", "-f", "docker-compose.yml", "-f", str(OVERLAY), "config", "--format", "json"]
config = json.loads(subprocess.check_output(command, cwd=ROOT, text=True))
errors = []
for name, service in config["services"].items():
    for port in service.get("ports", []):
        if port.get("host_ip") != "127.0.0.1":
            errors.append(f"{name}: unsafe published port {port}")
    if service.get("privileged"):
        errors.append(f"{name}: privileged container")
    if service.get("network_mode") == "host":
        errors.append(f"{name}: host network mode")
    for volume in service.get("volumes", []):
        if volume.get("source") == "/var/run/docker.sock":
            errors.append(f"{name}: Docker socket mount")
postgres = config["services"].get("postgres", {})
if not any(v.get("target") == "/var/lib/postgresql/data" and v.get("type") == "volume" for v in postgres.get("volumes", [])):
    errors.append("postgres: persistent named data volume missing")
if errors:
    print("\n".join(errors), file=sys.stderr)
    sys.exit(1)
print(f"PASS: {len(config['services'])} services checked; published ports are loopback-only")
