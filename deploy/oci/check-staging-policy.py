#!/usr/bin/env python3
"""Validate isolated staging Compose resource/security policy; no Docker needed."""
import sys
from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parents[2]
COMPOSE=ROOT/"deploy/oci/compose.staging.yml"
SERVICES=("postgres","redis","identity","trust","registry")
MAX_MEMORY_MIB=2048

def check(config):
    errors=[]
    services=config.get("services",{})
    if set(services)!=set(SERVICES):
        errors.append("staging service inventory differs from approved minimal stack")
    total=0
    for name in SERVICES:
        svc=services.get(name,{})
        mem=svc.get("mem_limit")
        if not isinstance(mem,str) or not mem.lower().endswith("m") or not mem[:-1].isdigit():
            errors.append(f"{name}: explicit MiB memory limit required")
        else:
            total+=int(mem[:-1])
        if not isinstance(svc.get("pids_limit"),int) or svc["pids_limit"]<1:
            errors.append(f"{name}: PID limit required")
        if svc.get("privileged") or svc.get("network_mode")=="host":
            errors.append(f"{name}: privileged/host networking prohibited")
        if svc.get("ports"):
            errors.append(f"{name}: published ports prohibited")
        if "no-new-privileges:true" not in svc.get("security_opt",[]):
            errors.append(f"{name}: privilege escalation protection required")
        if svc.get("restart")!="unless-stopped":
            errors.append(f"{name}: unexpected restart policy")
    if total>MAX_MEMORY_MIB:
        errors.append(f"staging memory budget {total} MiB exceeds {MAX_MEMORY_MIB} MiB")
    if not config.get("volumes",{}).get("staging-postgres") == None:
        # YAML null is valid for a named volume; non-null configuration is reviewed separately.
        pass
    if "staging-postgres" not in config.get("volumes",{}):
        errors.append("persistent staging PostgreSQL volume missing")
    return errors

if __name__=="__main__":
    try:
        config=yaml.safe_load(COMPOSE.read_text())
        errors=check(config)
    except (OSError,ValueError,yaml.YAMLError) as exc:
        print(f"BLOCKED: staging policy unreadable: {exc}",file=sys.stderr)
        raise SystemExit(3)
    if errors:
        print("BLOCKED: "+"; ".join(errors),file=sys.stderr)
        raise SystemExit(3)
    print("PASS: isolated staging resource and security policy")
