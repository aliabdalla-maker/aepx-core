"""Single-shot MCP recovery worker for an external scheduler.

Quarantines stale dispatches only. Never sends or retries MCP requests.
Requires an explicit tenant allowlist and a dedicated scheduler invocation.
"""
import os
from sqlalchemy import text
from .main import SessionLocal
from .mcp_execution214 import reconcile_stale

def run_once() -> dict[str, int]:
    if os.getenv("IDE_MCP_RECOVERY_ENABLED") != "true":
        raise PermissionError("Recovery scheduler not explicitly enabled")
    age = int(os.getenv("IDE_MCP_RECOVERY_AGE_SECONDS", "300"))
    if not 30 <= age <= 86400:
        raise ValueError("Invalid recovery age")
    tenants = [x.strip() for x in os.getenv("IDE_MCP_RECOVERY_TENANTS", "").split(",") if x.strip()]
    if not tenants or len(tenants) != len(set(tenants)):
        raise ValueError("Explicit unique recovery tenant allowlist required")
    counts = {}
    for tenant in tenants:
        if len(tenant) > 128:
            raise ValueError("Invalid tenant identifier")
        with SessionLocal() as db:
            counts[tenant] = reconcile_stale(db, tenant, age)
    return counts

if __name__ == "__main__":
    # Only counts are printed; never log credentials or provider evidence.
    print(run_once())
