-- Staging-only outbox lease migration; reviewed migration role required.
BEGIN;
ALTER TABLE hitl.outbox ADD COLUMN IF NOT EXISTS lease_owner text;
ALTER TABLE hitl.outbox ADD COLUMN IF NOT EXISTS leased_until timestamptz;
ALTER TABLE hitl.outbox ADD COLUMN IF NOT EXISTS next_attempt_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE hitl.outbox ADD COLUMN IF NOT EXISTS last_error text;
ALTER TABLE hitl.outbox DROP CONSTRAINT IF EXISTS outbox_status_check;
ALTER TABLE hitl.outbox ADD CONSTRAINT outbox_status_check
 CHECK (status IN ('pending','leased','delivered','dead'));
CREATE INDEX IF NOT EXISTS outbox_dispatch_idx
 ON hitl.outbox(tenant_id,status,next_attempt_at,leased_until);
COMMIT;
