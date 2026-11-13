-- Operator recovery audit for HITL dead letters. Apply in isolated staging first.
BEGIN;
CREATE TABLE IF NOT EXISTS hitl.outbox_recovery_audit (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 tenant_id uuid NOT NULL,
 event_id uuid NOT NULL,
 operator_id text NOT NULL,
 ticket_id text NOT NULL,
 reason text NOT NULL,
 recorded_at timestamptz NOT NULL DEFAULT now(),
 CONSTRAINT recovery_event_fk FOREIGN KEY (event_id) REFERENCES hitl.outbox(id)
);
CREATE INDEX IF NOT EXISTS outbox_recovery_tenant_event_idx
 ON hitl.outbox_recovery_audit(tenant_id,event_id,recorded_at);
ALTER TABLE hitl.outbox_recovery_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE hitl.outbox_recovery_audit FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS outbox_recovery_tenant ON hitl.outbox_recovery_audit;
CREATE POLICY outbox_recovery_tenant ON hitl.outbox_recovery_audit
 USING (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
 WITH CHECK (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);
COMMIT;
