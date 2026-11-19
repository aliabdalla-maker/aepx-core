#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
echo "== AEP-X development security checks =="
echo "WARNING: docker-compose.yml includes development credentials. Never use for production."
echo "Checking Codespaces console bind address..."
docker compose -f compose.codespaces.yml config --format json | python3 -c '
import json,sys
data=json.load(sys.stdin)
ports=data["services"]["aepx-console"].get("ports",[])
assert ports and all(p.get("host_ip") in ("127.0.0.1","::1") for p in ports), ports
print("PASS: console published only to loopback")
'
echo "Core stack port bindings (review before startup):"
docker compose -f docker-compose.yml -f compose.codespaces-core.yml config --format json | python3 -c '
import json,sys
data=json.load(sys.stdin)
for name in ("postgres","redis","identity","trust","registry","memory","cache","governance","gateway"):
    for p in data["services"].get(name,{}).get("ports",[]):
        if p.get("host_ip") not in ("127.0.0.1","::1"):
            print("WARNING: %s publishes %s on all interfaces"%(name,p.get("published","?")))
'
