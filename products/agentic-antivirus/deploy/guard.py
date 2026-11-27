#!/usr/bin/env python3
"""Static fail-closed checks for the compose stack (OCI-02/05/09/14, INT-10, DLV-09).
Checks the files in COMPOSE_FILE (colon-separated, as docker compose reads it; default compose.yml), so
deploy.sh validates exactly the overlay it is about to start (production, cohost or staging).
Uses `docker compose config` (no daemon or containers needed)."""
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(os.environ.get("AAV_COMPOSE_DIR") or Path(__file__).resolve().parent)
ALWAYS_FREE = {"ocpu": 4.0, "memory_gb": 24.0}   # tenancy-wide A1 allowance; verify current figures in preflight
FILES = [f for f in os.environ.get("COMPOSE_FILE", "compose.yml").split(":") if f]
env = dict(os.environ, AAV_POSTGRES_PASSWORD="x" * 32, AAV_APP_DB_PASSWORD="y" * 32,
           AAV_SIGNING_KEY_PATH=str(HERE / "guard.py"))
env.setdefault("AAV_PROXY_NETWORK", "guard-check")
env.pop("COMPOSE_FILE", None)
args = [a for f in FILES for a in ("-f", str(HERE / f))]
cfg = json.loads(subprocess.check_output(["docker", "compose", *args, "config", "--format", "json"],
                                         env=env, text=True))
errors, cpu, mem = [], 0.0, 0
for name, s in cfg["services"].items():
    for p in s.get("ports", []):
        if p.get("host_ip") != "127.0.0.1":
            errors.append(f"{name}: port {p} is not loopback-only")
    if s.get("privileged") or s.get("network_mode") == "host":
        errors.append(f"{name}: privileged or host networking")
    for v in s.get("volumes", []):
        if v.get("source") == "/var/run/docker.sock":
            errors.append(f"{name}: docker socket mounted")
    if "mem_limit" not in s or "cpus" not in s:
        errors.append(f"{name}: missing mem_limit/cpus")
    cpu += float(s.get("cpus", 0))
    mem += int(s.get("mem_limit", 0))
    envs = json.dumps(s.get("environment", {})).lower()
    for marker in ("aws_", "azure_", "oci_lb", "loadbalancer"):
        if marker in envs:
            errors.append(f"{name}: references a chargeable service ({marker})")
if "aav_signing_key" not in cfg.get("secrets", {}):
    errors.append("signing key must be a compose secret, not an environment variable")
if cpu > ALWAYS_FREE["ocpu"] or mem / 1024 ** 3 > ALWAYS_FREE["memory_gb"]:
    errors.append(f"resource totals {cpu} OCPU / {mem / 1024 ** 3:.1f} GB exceed the Always Free A1 allowance")
report = {"files": FILES, "services": len(cfg["services"]), "cpus_total": round(cpu, 2), "memory_gb_total": round(mem / 1024 ** 3, 2),
          "errors": errors}
print(json.dumps(report, indent=1))
sys.exit(1 if errors else 0)
