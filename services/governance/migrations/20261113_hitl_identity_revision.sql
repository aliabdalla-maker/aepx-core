-- Monotonic IdP snapshot sequence. Apply before deploying revised publisher.
ALTER TABLE hitl.identity_authority_sync
  ADD COLUMN IF NOT EXISTS revision bigint NOT NULL DEFAULT 0
  CHECK (revision >= 0);
-- For existing installations, mark authority unhealthy until a trusted
-- full snapshot with a revision greater than zero is published.
UPDATE hitl.identity_authority_sync SET healthy=false;
