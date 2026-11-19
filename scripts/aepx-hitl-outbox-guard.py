"""Static guard for staging HITL migration ordering and worker fencing."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
base=(ROOT/"db/migrations/20261113_hitl_staging.sql").read_text()
lease=(ROOT/"db/migrations/20261113_hitl_outbox_lease.sql").read_text()
worker=(ROOT/"services/governance/app/hitl_outbox.py").read_text()
assert "FORCE ROW LEVEL SECURITY" in base
assert "UNIQUE(tenant_id,idempotency_key)" in base
assert "ADD COLUMN IF NOT EXISTS leased_until" in lease
assert "ADD COLUMN IF NOT EXISTS next_attempt_at" in lease
assert "FOR UPDATE SKIP LOCKED" in worker
assert "AND attempts=%s AND leased_until>now()" in worker
print("HITL staging schema and lease fencing static invariants passed")
