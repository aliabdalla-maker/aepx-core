#!/usr/bin/env python3
"""Static fail-closed guard for release readiness. No secrets are printed."""
import json, pathlib, sys
root=pathlib.Path(".")
compose=(root/"docker-compose.yml").read_text()
findings=[]
for marker in ("aepx_dev_only","5432:5432","6379:6379","8000:8000"):
    if marker in compose:
        findings.append({"code":"DEV_ONLY_CONFIG","marker":marker,"severity":"blocker",
                         "message":"Reference Compose contains development credential or exposed port; not production-safe"})
report={"production_eligible":not findings,"findings":findings,
        "scope":"Limited static guard, not a full vulnerability scan"}
path=root/"artifacts/aepx-static-security.json"
path.parent.mkdir(parents=True,exist_ok=True)
path.write_text(json.dumps(report,indent=2)+"\n")
print(f"Production eligibility: {report['production_eligible']}; findings: {len(findings)}; report: {path}")
if "--production-gate" in sys.argv and findings:sys.exit(1)
