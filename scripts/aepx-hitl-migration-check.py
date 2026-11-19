#!/usr/bin/env python3
"""Static fail-closed inspection of the HITL staging migration. No database access."""
import json
import pathlib
import re
import sys

MIGRATION=pathlib.Path(__file__).resolve().parents[1]/"db/migrations/20261113_hitl_staging.sql"
TABLES=("approvals","events","outbox")
def inspect(sql):
    issues=[]
    for table in TABLES:
        target=f"hitl.{table}"
        for expected in (f"ALTER TABLE {target} ENABLE ROW LEVEL SECURITY",
                         f"ALTER TABLE {target} FORCE ROW LEVEL SECURITY",
                         f"DROP POLICY IF EXISTS {table}_tenant ON {target}",
                         f"CREATE POLICY {table}_tenant ON {target}"):
            if expected not in sql:issues.append("missing: "+expected)
        match=re.search(rf"CREATE POLICY {table}_tenant ON hitl\.{table}(.*?);",sql,re.S)
        if not match or "app.tenant_id" not in match.group(1) or "WITH CHECK" not in match.group(1):
            issues.append("tenant RLS USING/WITH CHECK missing: "+table)
    if "UNIQUE(tenant_id,idempotency_key)" not in sql:
        issues.append("outbox tenant-scoped idempotency constraint missing")
    if "CHECK (requester_id <> approver_id OR approver_id IS NULL)" not in sql:
        issues.append("self-approval constraint missing")
    return issues
def main():
    issues=inspect(MIGRATION.read_text())
    report={"migration":str(MIGRATION.relative_to(MIGRATION.parents[1])),"static_only":True,
            "passed":not issues,"issues":issues}
    path=pathlib.Path("artifacts/aepx-hitl-migration-check.json")
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
    return 1 if issues else 0
if __name__=="__main__":sys.exit(main())
