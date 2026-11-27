"""Seeds a running control plane through its public API and the real agent with synthetic, sanitised data
(used for screenshots, the CI accessibility gate and the staging environment, OCI-16). Env: AAV_API,
AAV_PSQL (psql connection string to read the verification mail) or AAV_PSQL_CMD (a full psql command, e.g.
"docker compose -p agentic-antivirus-staging exec -T postgres psql -U aav_owner -d aav")."""
import json
import os
import pathlib
import shlex
import subprocess
import sys
import tempfile

import httpx

P = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(P / "agent"), str(P / "detection")]
from aav_agent.agent import Agent  # noqa: E402

B = os.environ.get("AAV_API", "http://127.0.0.1:8000")
c = httpx.Client(base_url=B)


def sql(q):
    cmd = shlex.split(os.environ["AAV_PSQL_CMD"]) if os.environ.get("AAV_PSQL_CMD") else ["psql", os.environ["AAV_PSQL"]]
    return subprocess.run([*cmd, "-tAc", q], capture_output=True, text=True, check=True).stdout.strip()


email = "ops@example.com"
r = c.post("/v1/auth/register", json={"email": email, "password": "demo password 123", "organisation": "Northwind Dental Group"}).json()
tok = sql(f"select payload->>'link' from aav.outbound_mail where to_email='{email}'").split("token=")[1]
c.post("/v1/auth/verify-email", json={"token": tok})
s = c.post("/v1/auth/login", json={"email": email, "password": "demo password 123"}).json()["access_token"]
h = {"Authorization": f"Bearer {s}", "X-Tenant-Id": r["tenant_id"]}
data = json.loads((P / "detection/rules/baseline.json").read_text())
c.post("/v1/updates", headers=h, json={"kind": "detections", "version": data["version"], "body": data["body"]})
c.post("/v1/policies", headers=h, json={"name": "default", "body": {"on_access": True, "on_execute": True, "auto_quarantine_known": True,
                                                                   "behaviour_rules": True, "isolation_allowed": True}})
agents = []
for host in ("reception-pc", "finance-lt"):
    t = c.post("/v1/enrollment-tokens", headers=h, json={}).json()["token"]
    a = Agent(tempfile.mkdtemp(), http=c, base_url=B)
    a.enrol(t, host)
    a.refresh_policy()
    a.refresh_updates()
    a.heartbeat()
    agents.append(a)
a = agents[1]
a.emit("process_start", {"pid": 5188, "process": "rundll32.exe", "parent": "powershell.exe",
                         "cmdline": "rundll32.exe C:\\Windows\\System32\\comsvcs.dll, MiniDump 704 C:\\Users\\Public\\l.dmp full"})
a.flush()
inc = c.get("/v1/incidents", headers=h).json()[0]
c.post(f"/v1/incidents/{inc['id']}/investigate", headers=h, json={})
print(json.dumps({"token": s, "tenant": r["tenant_id"], "incident": inc["id"]}))
