#!/usr/bin/env python3
"""Check resolved Compose ports for exposure. No third-party YAML dependency."""
import json, subprocess, sys, pathlib
cmd=["docker","compose","-f","docker-compose.yml","-f","compose.codespaces-core.yml","config","--format","json"]
p=subprocess.run(cmd,capture_output=True,text=True)
if p.returncode:
    print("FAIL: cannot resolve Compose configuration:",p.stderr[-500:],file=sys.stderr)
    sys.exit(2)
try:
    config=json.loads(p.stdout)
except json.JSONDecodeError as exc:
    print("FAIL: invalid Compose JSON:",exc,file=sys.stderr)
    sys.exit(2)
exposures=[]
for name,svc in config.get("services",{}).items():
    for port in svc.get("ports",[]) or []:
        if isinstance(port,str):
            exposures.append({"service":name,"port":port,"reason":"unparsed string mapping"})
            continue
        host=port.get("host_ip") or "0.0.0.0"
        if host not in ("127.0.0.1","::1","localhost"):
            exposures.append({"service":name,"published":str(port.get("published","")),"host_ip":host})
result={"safe_loopback_bindings":not exposures,"exposures":exposures,"scope":"Resolved Compose host bindings only; not firewall, IAM or secrets validation"}
path=pathlib.Path("artifacts/aepx-compose-exposure.json")
path.parent.mkdir(parents=True,exist_ok=True)
path.write_text(json.dumps(result,indent=2)+"\n")
print(f"Compose public bindings: {len(exposures)}; report: {path}")
if exposures and "--enforce" in sys.argv:sys.exit(1)
