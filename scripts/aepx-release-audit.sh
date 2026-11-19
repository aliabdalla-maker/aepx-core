#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
mkdir -p artifacts
out="artifacts/aepx-release-audit.json"
python3 - "$out" <<'PY'
import json,subprocess,sys,datetime
out=sys.argv[1]
checks=[]
def check(name,cmd):
    try:
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=180)
        checks.append(dict(name=name,passed=p.returncode==0,detail=(p.stderr or p.stdout)[-500:]))
    except Exception as e:
        checks.append(dict(name=name,passed=False,detail=str(e)))
check("devcontainer_json",["python3","-m","json.tool",".devcontainer/devcontainer.json"])
check("shell_syntax",["bash","-n","scripts/codespaces.sh","scripts/codespaces-start.sh","scripts/codespaces-verify.sh","scripts/codespaces-smoke.sh","scripts/codespaces-security-check.sh"])
check("console_compose",["docker","compose","-f","compose.codespaces.yml","config","--quiet"])
check("core_compose",["docker","compose","-f","docker-compose.yml","-f","compose.codespaces-core.yml","config","--quiet"])
check("console_security",["bash","scripts/codespaces-security-check.sh"])
check("console_runtime",["bash","scripts/codespaces-smoke.sh"])
result={"generated_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"checks":checks,"passed":sum(x["passed"] for x in checks),"total":len(checks),"production_ready":False,"note":"Local runtime checks are evidence only for this host; production security and integration remain unverified."}
with open(out,"w") as f:json.dump(result,f,indent=2)
print(json.dumps(result,indent=2))
sys.exit(0 if all(x["passed"] for x in checks) else 1)
PY
