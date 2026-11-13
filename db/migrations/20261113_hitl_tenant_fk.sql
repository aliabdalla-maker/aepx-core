-- Run only against an approved, backed-up HITL database.
-- Enforce tenant-aware approval/event references even for privileged maintenance.
BEGIN;
DO $$
BEGIN
 IF EXISTS (
   SELECT 1 FROM hitl.events e
   JOIN hitl.approvals a ON a.id=e.approval_id
   WHERE a.tenant_id<>e.tenant_id
 ) THEN
   RAISE EXCEPTION 'Cross-tenant HITL event reference detected';
 END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS hitl_approvals_tenant_id_id_uidx
 ON hitl.approvals(tenant_id,id);
ALTER TABLE hitl.events
 DROP CONSTRAINT IF EXISTS events_approval_id_fkey;
ALTER TABLE hitl.events
 ADD CONSTRAINT events_tenant_approval_fk
 FOREIGN KEY (tenant_id,approval_id)
 REFERENCES hitl.approvals(tenant_id,id) NOT VALID;
ALTER TABLE hitl.events VALIDATE CONSTRAINT events_tenant_approval_fk;
COMMIT;
